"""
QR 디코딩 (pyzbar) + 객체 검출 (ultralytics YOLOv8n).
무거운 모델 로드는 lazy import로 SIMULATE/오프라인 모드에서 건너뜀.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import config

log = logging.getLogger(__name__)


@dataclass
class QrResult:
    text: str
    bbox: tuple   # (x, y, w, h)


@dataclass
class Detection:
    cls: str
    conf: float
    bbox: tuple   # (x1, y1, x2, y2)


class Vision:
    def __init__(self):
        self._yolo = None
        self._frame_idx = 0

    def begin(self, load_yolo: bool = True):
        if not load_yolo or config.SIMULATE:
            log.info("[vision] YOLO disabled (sim or skip)")
            return
        try:
            from ultralytics import YOLO
            self._yolo = YOLO(config.YOLO_MODEL)
            log.info(f"[vision] YOLO loaded: {config.YOLO_MODEL}")
        except Exception as e:
            log.warning(f"[vision] YOLO load failed: {e}")

    def detect_qr(self, frame: np.ndarray) -> list[QrResult]:
        if config.SIMULATE or frame is None:
            return []
        try:
            from pyzbar.pyzbar import decode
            results = []
            for d in decode(frame):
                results.append(QrResult(
                    text=d.data.decode("utf-8", errors="ignore"),
                    bbox=(d.rect.left, d.rect.top, d.rect.width, d.rect.height),
                ))
            return results
        except Exception as e:
            log.debug(f"[vision] QR error: {e}")
            return []

    def detect_objects(self, frame: np.ndarray) -> list[Detection]:
        self._frame_idx += 1
        if self._yolo is None or frame is None:
            return []
        # 5프레임마다만 실행 (CPU 부담 ↓)
        if self._frame_idx % config.YOLO_INTERVAL_FRAMES != 0:
            return []
        try:
            results = self._yolo.predict(frame, conf=config.YOLO_CONF_THRESHOLD,
                                         verbose=False)
            out = []
            for r in results:
                if r.boxes is None: continue
                for b in r.boxes:
                    cls_id = int(b.cls[0])
                    name = self._yolo.names.get(cls_id, str(cls_id))
                    xyxy = b.xyxy[0].tolist()
                    out.append(Detection(
                        cls=name, conf=float(b.conf[0]),
                        bbox=tuple(xyxy),
                    ))
            return out
        except Exception as e:
            log.debug(f"[vision] YOLO error: {e}")
            return []
