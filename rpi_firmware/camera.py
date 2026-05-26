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
    """단일 카메라 래퍼. kind='picam' 또는 'webcam'."""

    def __init__(self, kind: str = "picam"):
        self.kind = kind
        self._picam = None
        self._cap = None
        self._sim = config.SIMULATE
        self._res = config.PICAM_RES if kind == "picam" else config.WEBCAM_RES

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

        # webcam — picam과 동시 사용을 위해 V4L2 백엔드 + MJPEG 강제 + 버퍼 1
        # raw YUYV 모드면 USB 2.0 대역폭을 거의 다 잡아먹어서 picam이 동작 못 함.
        # MJPEG는 카메라가 압축해서 보내므로 대역폭 1/10로 줄어들어 동시 사용 가능.
        try:
            import cv2
            self._cap = cv2.VideoCapture(config.WEBCAM_INDEX, cv2.CAP_V4L2)
            # 1) MJPEG 포맷 강제 (USB 대역폭 절감 — 가장 중요)
            fourcc = cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')
            self._cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            # 2) 해상도
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._res[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._res[1])
            # 3) 버퍼 1프레임 (지연 최소화 + 메모리 절감)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # 4) FPS 캡 (불필요한 대역폭 방지)
            self._cap.set(cv2.CAP_PROP_FPS, 15)

            ok = self._cap.isOpened()
            if ok:
                actual_fourcc = int(self._cap.get(cv2.CAP_PROP_FOURCC))
                fcc = bytes([actual_fourcc & 0xff, (actual_fourcc >> 8) & 0xff,
                             (actual_fourcc >> 16) & 0xff, (actual_fourcc >> 24) & 0xff]).decode("ascii", "ignore")
                log.info(f"[camera:webcam] index={config.WEBCAM_INDEX} fourcc={fcc!r} "
                         f"{int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
                if "MJPG" not in fcc.upper():
                    log.warning(f"[camera:webcam] MJPEG가 거부됨(현재={fcc}). USB 대역폭 부족으로 picam과 충돌 가능. "
                                f"v4l2-ctl --device=/dev/video{config.WEBCAM_INDEX} --list-formats-ext 로 지원 포맷 확인")
            return ok
        except Exception as e:
            log.error(f"[camera:webcam] failed: {e}")
            return False

    def read(self) -> Optional[np.ndarray]:
        """BGR 또는 RGB 프레임 반환 (numpy uint8 HxWx3). 실패 시 None."""
        if self._sim:
            return np.zeros((self._res[1], self._res[0], 3), dtype=np.uint8)

        if self._picam:
            return self._picam.capture_array()   # RGB

        if self._cap:
            ok, frame = self._cap.read()
            return frame if ok else None        # BGR
        return None

    def close(self):
        if self._picam:
            self._picam.stop()
            self._picam = None
        if self._cap:
            self._cap.release()
            self._cap = None
