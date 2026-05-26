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
        self._zbar_ok = False
        self._qr_attempts = 0
        self._qr_hits = 0
        self._qr_last_log = 0.0

    def begin(self, load_yolo: bool = True):
        # pyzbar 사전 점검 (QR 검출 필수)
        try:
            from pyzbar.pyzbar import decode  # noqa: F401
            self._zbar_ok = True
            log.info("[vision] pyzbar 로드 OK — QR 검출 가능")
        except ImportError as e:
            self._zbar_ok = False
            log.error(f"[vision] ❌ pyzbar 미설치 — QR 검출 불가. "
                      f"해결: sudo apt install -y libzbar0 && pip install pyzbar. ({e})")

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
        if not self._zbar_ok:
            return []   # begin()에서 이미 명확히 경고함

        import time as _t
        self._qr_attempts += 1
        try:
            from pyzbar.pyzbar import decode
            # RGB888 frame을 그대로 넘김 — pyzbar는 RGB/BGR/grayscale 모두 처리.
            # 인식률 향상 위해 추가로 grayscale 변환 시도 (실패해도 원본으로 fallback).
            decoded = decode(frame)
            if not decoded:
                # 못 잡으면 grayscale 변환 후 재시도 (저조도/회전 케이스 도움)
                try:
                    import cv2
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    decoded = decode(gray)
                except Exception:
                    pass

            results = []
            for d in decoded:
                text = d.data.decode("utf-8", errors="ignore")
                results.append(QrResult(
                    text=text,
                    bbox=(d.rect.left, d.rect.top, d.rect.width, d.rect.height),
                ))
            if results:
                self._qr_hits += 1
            # 5초마다 통계 보고
            now = _t.time()
            if now - self._qr_last_log > 5:
                if self._qr_attempts > 0:
                    log.info(f"[vision] QR 5초 통계: {self._qr_hits}/{self._qr_attempts} "
                             f"감지 (성공률 {100*self._qr_hits/self._qr_attempts:.0f}%)")
                self._qr_attempts = 0
                self._qr_hits = 0
                self._qr_last_log = now
            return results
        except Exception as e:
            log.warning(f"[vision] QR error: {e}")
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

    def detect_persons(self, frame: np.ndarray) -> list[Detection]:
        """detect_objects에서 person 클래스만 필터링."""
        return [d for d in self.detect_objects(frame) if d.cls == "person"]

    def detect_obstacles(self, frame: np.ndarray) -> list[Detection]:
        """후방 카메라용: 사람 + 사물 모두 장애물로 취급.
        쓰레기통(빈) 클래스는 미션 대상이므로 제외 — 단 YOLO 학습 안 됐으면 어차피 없음."""
        # YOLO COCO 클래스 중 통상 "장애물"로 봐야 할 것들 + 모든 사물 포괄
        # bin/trash can은 YOLO 기본 모델에 없으므로 제외 처리 불필요
        return self.detect_objects(frame)
