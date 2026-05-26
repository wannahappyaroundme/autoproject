"""
RPi 자율 동작 메인 진입점.
실행: python -m rpi_firmware.main  (rpi_firmware 부모 디렉토리에서)

오프라인 자율 동작:
  - 코드 시작 시 미션(빈 시퀀스)을 주입
  - Arduino + 카메라(CSI=전방 QR, USB=후방 사람감지) 핸드셰이크
  - 100ms 제어 루프 (Arduino) + 5Hz 비전 루프 (전/후방 각각 별도 스레드)
  - 모든 빈 수거 완료 시 종료
"""
import logging
import signal
import sys
import threading
import time

from . import config
from .serial_link import SerialLink
from .camera import Camera
from .vision import Vision
from .planner import MissionPlanner, Mission, Waypoint, State
from .human_guard import ObstacleGuard


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_default_mission() -> Mission:
    """시제품 테스트용 기본 미션. seed_data_prototype.py와 동일한 4개 빈."""
    return Mission(
        bins=[
            Waypoint(name="BIN-01", qr_id="BIN-01"),
            Waypoint(name="BIN-02", qr_id="BIN-02"),
            Waypoint(name="BIN-03", qr_id="BIN-03"),
            Waypoint(name="BIN-04", qr_id="BIN-04"),
        ],
        depot=Waypoint(name="DEPOT", qr_id="DEPOT", is_depot=True),
    )


class App:
    def __init__(self):
        self.link = SerialLink()
        # cam_front: 자율 미션 fps는 config 기본 (15). cam_rear: web_control과 동일하게 30 강제.
        # USB 카메라는 15보다 30에서 안정적 (저가 칩셋 fps mode lock-in 이슈).
        self.cam_front = Camera("picam")
        self.cam_rear = Camera("webcam", fps_override=30)
        self.vision = Vision()
        self.obstacle_guard = ObstacleGuard()
        self.planner = MissionPlanner(self.link, self.vision, self.obstacle_guard)
        self._stop = threading.Event()
        self._latest_qrs = []
        self._qr_lock = threading.Lock()
        # 카메라 open 결과 — begin() 호출 후 채워짐
        self.cam_front_ok = False
        self.cam_rear_ok = False
        # 라이브 시각 검증용 — vision_loop이 최신 프레임 + 검출 결과 저장.
        # pickup_test 같은 외부 도구가 frame_lock으로 안전하게 가져가 mjpeg 스트림.
        self._frame_lock = threading.Lock()
        self._latest_front_frame = None
        self._latest_front_qrs = []
        self._latest_rear_frame = None
        self._latest_rear_obstacles = []

    def begin(self) -> bool:
        if not self.link.open():
            logging.error("Arduino 연결 실패")
            return False
        # 카메라는 실패해도 진행 (비전 없이 거리 기반 동작). 결과는 외부 상태 표시용으로 저장.
        self.cam_front_ok = self.cam_front.open()
        self.cam_rear_ok = self.cam_rear.open()
        if not self.cam_front_ok:
            logging.warning("전방 카메라(CSI) 열기 실패 — picam 점유 중일 수 있음 (이전 web_control 좀비?)")
        if not self.cam_rear_ok:
            logging.warning("후방 카메라(USB) 열기 실패 — WEBCAM_INDEX 확인")
        self.vision.begin(load_yolo=True)
        return True

    def shutdown(self):
        self._stop.set()
        self.link.stop()
        time.sleep(0.2)
        self.link.close()
        self.cam_front.close()
        self.cam_rear.close()
        logging.info("shutdown done")

    def front_vision_loop(self):
        """CSI 카메라 → QR 검출. planner가 조향에 사용. 프레임도 시각 검증용으로 저장."""
        period = 1.0 / config.VISION_LOOP_HZ
        log = logging.getLogger("front_vision")
        frame_count = 0
        last_log = time.time()
        while not self._stop.is_set():
            t0 = time.time()
            frame = self.cam_front.read()
            if frame is not None:
                frame_count += 1
                qrs = self.vision.detect_qr(frame)
                with self._qr_lock:
                    self._latest_qrs = qrs
                with self._frame_lock:
                    # .copy()로 메모리 안정 (picamera2/cv2의 zero-copy 동작 안전화)
                    self._latest_front_frame = frame.copy() if hasattr(frame, 'copy') else frame
                    self._latest_front_qrs = qrs
            # 5초마다 받은 프레임 수 보고 (디버그)
            if time.time() - last_log > 5:
                log.info(f"전방 5초간 {frame_count} 프레임 ({frame_count/5:.1f}fps)")
                frame_count = 0
                last_log = time.time()
            elapsed = time.time() - t0
            time.sleep(max(0, period - elapsed))

    def rear_vision_loop(self):
        """USB 웹캠 → 사람+사물 검출. obstacle_guard 갱신.
        read가 연속 실패하면 자동 백오프 (vision_loop이 block되지 않도록)."""
        period = 1.0 / config.VISION_LOOP_HZ
        log = logging.getLogger("rear_vision")
        frame_count = 0
        fail_streak = 0
        last_log = time.time()
        while not self._stop.is_set():
            t0 = time.time()
            # 연속 실패 시 백오프 — read 호출 자체를 일정 시간 skip
            # (USB select timeout이 10초 block하는 걸 매 200ms 호출 안 함)
            if fail_streak >= 3:
                time.sleep(2.0)   # 2초간 read 시도 X. 5분에 1번씩만 재시도.
                fail_streak = 0
                continue
            frame = self.cam_rear.read()
            if frame is not None:
                frame_count += 1
                fail_streak = 0
                obstacles = self.vision.detect_obstacles(frame)
                self.obstacle_guard.update_camera(len(obstacles))
                with self._frame_lock:
                    self._latest_rear_frame = frame.copy() if hasattr(frame, 'copy') else frame
                    self._latest_rear_obstacles = obstacles
            else:
                fail_streak += 1
            if time.time() - last_log > 5:
                log.info(f"후방 5초간 {frame_count} 프레임 ({frame_count/5:.1f}fps)")
                frame_count = 0
                last_log = time.time()
            elapsed = time.time() - t0
            time.sleep(max(0, period - elapsed))

    def run(self, mission: Mission = None, stop_at: State = None,
            auto_terminate: bool = True):
        """제어 루프 + 비전 루프 실행.
        - mission=None: planner.start() 호출 안 함 → IDLE 유지 (반자동 모드: 외부 trigger_start 대기).
        - stop_at: 디버그용. 해당 상태 진입 시 break.
        - auto_terminate=False: DONE/ABORTED여도 break 안 함. _stop.set()으로만 종료 (반자동 모드).
        """
        if mission is not None:
            self.planner.start(mission)
        threads = [
            threading.Thread(target=self.front_vision_loop, daemon=True),
            threading.Thread(target=self.rear_vision_loop, daemon=True),
        ]
        for t in threads:
            t.start()

        period = 1.0 / config.CONTROL_LOOP_HZ
        log = logging.getLogger("main")

        while not self._stop.is_set():
            t0 = time.time()

            with self._qr_lock:
                qrs = list(self._latest_qrs)
            self.planner.step(self.link.latest, qrs)

            if stop_at and self.planner.state == stop_at:
                log.info(f"mission paused at {stop_at.value} (debug stop)")
                self.link.stop()
                break

            if auto_terminate and self.planner.state in (State.DONE, State.ABORTED):
                log.info(f"mission ended: {self.planner.state.value}")
                break

            elapsed = time.time() - t0
            time.sleep(max(0, period - elapsed))


def main():
    setup_logging()
    app = App()

    def on_sigint(signum, frame):
        logging.info("SIGINT received")
        app.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    if not app.begin():
        sys.exit(1)

    try:
        app.run(build_default_mission())
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
