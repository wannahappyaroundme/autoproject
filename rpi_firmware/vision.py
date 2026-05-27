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
        self._hog = None      # 🆕 OpenCV HOG fallback (YOLO 없을 때 사람 감지)
        # 🆕 Haar Cascade detectors — 얼굴/상반신 (HOG는 전신만이라 가까이서 안 잡힘)
        self._face_cascade = None
        self._upperbody_cascade = None
        self._frame_idx = 0
        self._hog_idx = 0     # HOG 자체 throttle용 (별도 카운터)
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

        # 🆕 YOLO 실패 시 OpenCV HOG + Haar Cascade fallback — 사람만, 가벼움.
        # HOG: 전신 (멀리 있는 사람). Haar: 얼굴/상반신 (가까이 있는 사람).
        # 세 detector OR 조합으로 recall 향상.
        if self._yolo is None:
            try:
                import cv2
                self._hog = cv2.HOGDescriptor()
                self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                # Haar Cascade — OpenCV 내장 XML 사용
                haar_dir = cv2.data.haarcascades
                self._face_cascade = cv2.CascadeClassifier(
                    haar_dir + "haarcascade_frontalface_default.xml")
                self._upperbody_cascade = cv2.CascadeClassifier(
                    haar_dir + "haarcascade_upperbody.xml")
                # 로드 실패 시 empty() True
                if self._face_cascade.empty():
                    self._face_cascade = None
                if self._upperbody_cascade.empty():
                    self._upperbody_cascade = None
                msg = "[vision] HOG fallback 활성 — "
                parts = []
                if self._hog is not None:               parts.append("HOG(전신)")
                if self._face_cascade is not None:      parts.append("Haar(얼굴)")
                if self._upperbody_cascade is not None: parts.append("Haar(상반신)")
                log.info(msg + " + ".join(parts) + " 조합")
            except Exception as e:
                log.warning(f"[vision] HOG/Haar fallback 실패: {e}")

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

    def detect_front_obstacles(self, frame: np.ndarray) -> list[Detection]:
        """🆕 전방 카메라용: 사람 + 사물 감지 (장애물 회피).
        YOLO 있으면 모든 object 감지 (정확). 없으면 OpenCV HOG + Haar(얼굴/상반신) 조합.

        주의: COCO YOLO는 쓰레기통(trash can/bin) 클래스가 없어 빈을 사람/object로 오인할
        수 있음. 빈 접근 상태(_BIN_APPROACH_STATES)에서는 planner가 이 신호를 무시함."""
        if self._yolo is not None:
            return self.detect_objects(frame)
        if self._hog is not None or self._face_cascade is not None or self._upperbody_cascade is not None:
            return self._detect_persons_fallback(frame)
        return []

    def _detect_persons_fallback(self, frame: np.ndarray) -> list[Detection]:
        """🆕 HOG(전신) + Haar(얼굴) + Haar(상반신) 조합 사람 감지.
        하나라도 감지되면 person. recall ↑ — 가까이서 상반신/얼굴만 보여도 잡힘.
        Detection.cls = 'person' (planner의 person 트리거 호환)."""
        if frame is None:
            return []
        # YOLO_INTERVAL_FRAMES(5)와 같게 throttle
        self._hog_idx += 1
        if self._hog_idx % config.YOLO_INTERVAL_FRAMES != 0:
            return []
        try:
            import cv2
            h, w = frame.shape[:2]
            # 다운샘플 — 속도 ↑ (RPi 4에서 320×w 권장)
            if w > 320:
                scale = 320 / w
                small = cv2.resize(frame, (320, int(h * scale)))
            else:
                scale = 1.0
                small = frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            out = []
            seen = []   # (x1,y1,x2,y2) — 중복 제거용

            def add_bbox(x, y, bw, bh, src):
                x1 = int(x / scale); y1 = int(y / scale)
                x2 = int((x + bw) / scale); y2 = int((y + bh) / scale)
                # 같은 사람이 여러 detector에 잡히면 큰 IOU → 중복 제외
                for sx1, sy1, sx2, sy2 in seen:
                    if abs(x1 - sx1) < 30 and abs(y1 - sy1) < 30:
                        return
                seen.append((x1, y1, x2, y2))
                out.append(Detection(cls="person", conf=0.8, bbox=(x1, y1, x2, y2)))

            # 1) HOG — 전신
            if self._hog is not None:
                try:
                    boxes, _ = self._hog.detectMultiScale(
                        small, winStride=(8, 8), padding=(8, 8), scale=1.05)
                    for (x, y, bw, bh) in boxes:
                        add_bbox(x, y, bw, bh, "hog")
                except Exception:
                    pass

            # 2) Haar — 얼굴
            if self._face_cascade is not None:
                try:
                    faces = self._face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                    for (x, y, bw, bh) in faces:
                        add_bbox(x, y, bw, bh, "face")
                except Exception:
                    pass

            # 3) Haar — 상반신
            if self._upperbody_cascade is not None:
                try:
                    bodies = self._upperbody_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40))
                    for (x, y, bw, bh) in bodies:
                        add_bbox(x, y, bw, bh, "upper")
                except Exception:
                    pass

            return out
        except Exception as e:
            log.debug(f"[vision] fallback detect error: {e}")
            return []

    def detect_close_bin(self, frame: np.ndarray) -> bool:
        """🆕 프레임이 거의 흰/검 두 가지 색뿐인지 검사.
        QR이 카메라 시야를 가득 채워 finder pattern 인식 불가능한 상태 = 빈이 매우 가까이 있음.
        이 신호를 planner의 거리 가드 통과 조건으로 사용.

        검사 (둘 다 만족 시 True):
          1) 채도(S) 평균 < CLOSE_BIN_SAT_MAX → 화면이 회색조 (흰/검 위주, 컬러 아님)
          2) 명도(V) 양극화: (V<DARK) + (V>BRIGHT) 비율 합 > CLOSE_BIN_POLAR_MIN
             → 중간 톤이 거의 없음 = 흑/백 두 그룹

        다운샘플(50×50)로 빠르게 처리 — 5Hz vision_loop에서 부담 없음.
        """
        if frame is None or config.SIMULATE:
            return False
        try:
            import cv2
            small = cv2.resize(frame, (50, 50))
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            sat = hsv[:, :, 1]
            val = hsv[:, :, 2]

            # 1) 채도 검사 — 회색조 여부
            if float(sat.mean()) > config.CLOSE_BIN_SAT_MAX:
                return False

            # 2) 명도 양극화 — 흑/백 비율
            n = val.size
            dark = int((val < config.CLOSE_BIN_DARK_V).sum())
            bright = int((val > config.CLOSE_BIN_BRIGHT_V).sum())
            polar_ratio = (dark + bright) / n
            return polar_ratio > config.CLOSE_BIN_POLAR_MIN
        except Exception as e:
            log.debug(f"[vision] detect_close_bin error: {e}")
            return False
