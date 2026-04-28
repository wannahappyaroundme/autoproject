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

        # webcam
        try:
            import cv2
            self._cap = cv2.VideoCapture(config.WEBCAM_INDEX)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._res[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._res[1])
            ok = self._cap.isOpened()
            if ok: log.info(f"[camera:webcam] index={config.WEBCAM_INDEX}")
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
