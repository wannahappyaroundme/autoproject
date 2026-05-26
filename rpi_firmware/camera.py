"""
카메라 추상화: RPi Camera Module 3 (CSI) + 웹캠 AU100 (USB).
SIMULATE 모드에서는 검은 프레임 반환.
"""
import logging
import numpy as np
from typing import Optional, Tuple

from . import config

log = logging.getLogger(__name__)


class Camera:
    """단일 카메라 래퍼. kind='picam' 또는 'webcam'.
    fps_override: 해당 인스턴스 fps 강제. None이면 config 기본값 사용.
                  (web_control은 시각 검증용으로 30 권장, 자율 미션은 15 권장)"""

    def __init__(self, kind: str = "picam", fps_override: int = None):
        self.kind = kind
        self._picam = None
        self._cap = None
        self._sim = config.SIMULATE
        self._res = config.PICAM_RES if kind == "picam" else config.WEBCAM_RES
        default_fps = config.PICAM_FPS if kind == "picam" else config.WEBCAM_FPS
        self._fps = fps_override if fps_override is not None else default_fps

    def open(self) -> bool:
        if self._sim:
            log.info(f"[camera:{self.kind}] SIMULATE")
            return True

        if self.kind == "picam":
            try:
                from picamera2 import Picamera2
                self._picam = Picamera2()
                cfg = self._picam.create_preview_configuration(
                    main={"size": self._res, "format": "RGB888"}
                )
                self._picam.configure(cfg)
                self._picam.start()
                log.info(f"[camera:picam] started {self._res}")
                return True
            except Exception as e:
                log.error(f"[camera:picam] failed: {e}")
                return False

        # webcam — 단계적 fallback으로 다양한 환경 호환.
        # 1차: V4L2 + MJPG (이상적, USB 대역폭 1/10)
        # 2차: V4L2 + 기본 포맷 (MJPG 거부 시)
        # 3차: 자동 백엔드 (V4L2 백엔드 자체 거부 시)
        try:
            import cv2
        except ImportError:
            log.error("[camera:webcam] cv2 not installed")
            return False

        idx = config.WEBCAM_INDEX
        attempts = [
            ("V4L2+MJPG", cv2.CAP_V4L2, True),
            ("V4L2+default", cv2.CAP_V4L2, False),
            ("auto+MJPG", cv2.CAP_ANY, True),
            ("auto+default", cv2.CAP_ANY, False),
        ]
        import time as _time
        # 🛡️ 하드 타임아웃: USB cam이 응답 없을 때 begin() 전체가 90초+ 블로킹되는 사고 방지.
        # 이 시간 안에 못 열면 cam_rear_ok=False로 진행 (rear vision 없이 거리/IMU만 사용).
        # 10초 = (4 backend × (open 0.5 + warmup 1.0 + read 최대 2초)) + 여유 0.5s
        WEBCAM_OPEN_DEADLINE_S = 10.0
        deadline = _time.time() + WEBCAM_OPEN_DEADLINE_S

        # CAP_PROP_OPEN_TIMEOUT_MSEC / CAP_PROP_READ_TIMEOUT_MSEC는 OpenCV 4.5+에만 존재.
        # 없으면 V4L2 select() 10초 timeout이 그대로 적용되어 시도당 ~11초 → deadline 1시도밖에 못 함.
        OPEN_TIMEOUT = getattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", None)
        READ_TIMEOUT = getattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", None)
        if READ_TIMEOUT is None:
            log.warning(f"[camera:webcam] cv2 {cv2.__version__}: CAP_PROP_READ_TIMEOUT_MSEC 미지원 — "
                        f"V4L2 read가 10s까지 블로킹될 수 있음 (deadline 1시도만 가능)")

        for label, backend, want_mjpg in attempts:
            if _time.time() > deadline:
                log.warning(f"[camera:webcam] {WEBCAM_OPEN_DEADLINE_S:.0f}s 타임아웃 — 남은 시도 스킵")
                break
            try:
                cap = cv2.VideoCapture(idx, backend)
                # cv2가 지원하면 V4L2 select() timeout을 2초로 짧게 (기본 10초)
                if OPEN_TIMEOUT is not None:
                    cap.set(OPEN_TIMEOUT, 2000)
                if READ_TIMEOUT is not None:
                    cap.set(READ_TIMEOUT, 2000)
                if not cap.isOpened():
                    cap.release()
                    log.debug(f"[camera:webcam] {label} 시도: VideoCapture open 실패")
                    continue
                if want_mjpg:
                    cap.set(cv2.CAP_PROP_FOURCC,
                            cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._res[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._res[1])
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FPS, self._fps)

                # 🔑 USB 카메라 초기화 대기 — open 직후 즉시 read하면 첫 select timeout 가능.
                # 1.0s = USB enumerate 직후 첫 frame 생성에 충분한 여유.
                _time.sleep(1.0)

                # 첫 read는 1회만 시도 (실패 시 다음 backend로 빠르게 이동).
                # deadline 체크는 read 직전에만 (read 자체는 V4L2 select timeout에 묶임).
                if _time.time() > deadline:
                    cap.release()
                    log.warning(f"[camera:webcam] {label} 시도 전 타임아웃")
                    break
                ok, _ = cap.read()

                if not ok:
                    cap.release()
                    log.debug(f"[camera:webcam] {label} 시도: read 실패")
                    continue

                # 성공
                self._cap = cap
                fcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
                fcc = bytes([fcc_int & 0xff, (fcc_int >> 8) & 0xff,
                             (fcc_int >> 16) & 0xff, (fcc_int >> 24) & 0xff]).decode("ascii", "ignore")
                log.info(f"[camera:webcam] OK ({label}) index={idx} fourcc={fcc!r} "
                         f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
                if want_mjpg and "MJPG" not in fcc.upper():
                    log.warning(f"[camera:webcam] MJPG 요청했지만 실제 fourcc={fcc} — USB 대역폭 주의")
                return True
            except Exception as e:
                log.debug(f"[camera:webcam] {label} 시도 예외: {e}")
                continue

        # 모든 시도 실패
        elapsed = _time.time() - (deadline - WEBCAM_OPEN_DEADLINE_S)
        log.error(f"[camera:webcam] 모든 시도 실패 ({elapsed:.1f}s 소요). /dev/video{idx} 점유 중이거나 인덱스 잘못됨. "
                  f"sudo lsof /dev/video{idx} / v4l2-ctl --list-devices 확인")
        return False

    def read(self) -> Optional[np.ndarray]:
        """BGR 또는 RGB 프레임 반환 (numpy uint8 HxWx3). 실패 시 None.
        picam은 config.PICAM_ROTATION 만큼 회전 보정 (90/180/270)."""
        if self._sim:
            return np.zeros((self._res[1], self._res[0], 3), dtype=np.uint8)

        if self._picam:
            frame = self._picam.capture_array()   # RGB
            return self._apply_rotation(frame) if self.kind == "picam" else frame

        if self._cap:
            ok, frame = self._cap.read()
            return frame if ok else None        # BGR
        return None

    def _apply_rotation(self, frame):
        """picam 회전 보정 — 카메라 모듈이 비스듬히 부착됐을 때.
        cv2.rotate 결과를 ascontiguousarray로 메모리 정렬 보장 (imencode 안전)."""
        rot = config.PICAM_ROTATION
        if rot == 0 or frame is None:
            return frame
        try:
            import cv2
            import numpy as np
            if rot == 90:
                rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 180:
                rotated = cv2.rotate(frame, cv2.ROTATE_180)
            elif rot == 270:
                rotated = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            else:
                return frame
            return np.ascontiguousarray(rotated)
        except Exception as e:
            log.debug(f"[camera:picam] rotate failed: {e}")
        return frame

    def close(self):
        # picam: stop()만으로는 libcamera 파이프라인 핸들러가 풀리지 않는 경우가 있어
        # close()까지 호출 + 예외 무시. 풀리지 않으면 다음 실행에서 "Pipeline handler in use" 발생.
        if self._picam:
            try: self._picam.stop()
            except Exception: pass
            try: self._picam.close()
            except Exception: pass
            self._picam = None
        if self._cap:
            try: self._cap.release()
            except Exception: pass
            self._cap = None
