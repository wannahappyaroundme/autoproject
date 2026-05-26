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
        self.cam_front = Camera("picam")      # CSI: QR 인식 + 빈 위치 추정
        self.cam_rear = Camera("webcam")      # USB: 사람 감지(후방+측방)
        self.vision = Vision()
        self.obstacle_guard = ObstacleGuard()
        self.planner = MissionPlanner(self.link, self.vision, self.obstacle_guard)
        self._stop = threading.Event()
        self._latest_qrs = []
        self._qr_lock = threading.Lock()
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
        # 카메라는 실패해도 진행 (비전 없이 거리 기반 동작)
        self.cam_front.open()
        self.cam_rear.open()
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
        while not self._stop.is_set():
            t0 = time.time()
            frame = self.cam_front.read()
            if frame is not None:
                qrs = self.vision.detect_qr(frame)
                with self._qr_lock:
                    self._latest_qrs = qrs
                with self._frame_lock:
                    self._latest_front_frame = frame
                    self._latest_front_qrs = qrs
            elapsed = time.time() - t0
            time.sleep(max(0, period - elapsed))

    def rear_vision_loop(self):
        """USB 웹캠 → 사람+사물 검출. obstacle_guard 갱신.
        프레임 + 검출 결과를 시각 검증용으로 저장."""
        period = 1.0 / config.VISION_LOOP_HZ
        while not self._stop.is_set():
            t0 = time.time()
            frame = self.cam_rear.read()
            if frame is not None:
                obstacles = self.vision.detect_obstacles(frame)
                self.obstacle_guard.update_camera(len(obstacles))
                with self._frame_lock:
                    self._latest_rear_frame = frame
                    self._latest_rear_obstacles = obstacles
            elapsed = time.time() - t0
            time.sleep(max(0, period - elapsed))

    def run(self, mission: Mission, stop_at: State = None):
        """미션 실행. stop_at에 지정한 상태에 진입 시 정지(디버그용)."""
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

            if self.planner.state in (State.DONE, State.ABORTED):
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
