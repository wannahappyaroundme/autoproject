"""
QR bbox + 초음파 거리 → 빈 위치(bearing/distance) 추정.

알고리즘:
  - 빈을 향한 좌/우 각도(bearing_deg)는 QR bbox 중심의 화면 내 x좌표를 카메라
    HFOV에 매핑해 계산.
  - 거리는 1순위 전방 초음파(telem.front_cm), 2순위 bbox 폭(보조 검증·로깅용).
  - 미션의 target QR id와 매칭되는 검출만 사용. 일치 없으면 locked=False.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .vision import QrResult
from . import config


@dataclass
class BinTarget:
    qr_id: str
    bearing_deg: float     # 양수=우측, 음수=좌측, 0=정면
    distance_cm: float     # 전방 초음파 기준
    bbox_w: int            # bbox 폭(픽셀) — 거리 보조 검증용
    locked: bool           # 미션 target과 일치 여부

    @property
    def centered(self) -> bool:
        return abs(self.bearing_deg) < config.STEER_DEADZONE_DEG


def pick_target(
    qrs: list[QrResult],
    target_qr_id: Optional[str],
    front_cm: float,
    frame_w: int = None,
    hfov_deg: float = None,
) -> Optional[BinTarget]:
    """미션 target과 일치하는 QR을 골라 BinTarget 반환. 일치 없으면 None.

    frame_w/hfov_deg는 테스트에서 오버라이드 가능, 기본은 config 값.
    """
    if not qrs or not target_qr_id:
        return None
    fw = frame_w if frame_w is not None else config.PICAM_RES[0]
    fov = hfov_deg if hfov_deg is not None else config.HFOV_DEG

    match = next((q for q in qrs if q.text == target_qr_id), None)
    if match is None:
        return None

    x, _y, w, _h = match.bbox
    cx = x + w / 2.0
    bearing = (cx - fw / 2.0) / (fw / 2.0) * (fov / 2.0)
    return BinTarget(
        qr_id=match.text,
        bearing_deg=bearing,
        distance_cm=front_cm,
        bbox_w=w,
        locked=True,
    )


def steer_command_deg(bearing_deg: float) -> int:
    """bearing → 서보 절대 각도(0~180, 중앙=90). 데드존 내면 중앙복귀."""
    if abs(bearing_deg) < config.STEER_DEADZONE_DEG:
        return 90
    delta = config.STEER_KP * bearing_deg
    # ±45° 가동범위로 클램프(서보 자체는 0~180 가능하지만 조향에 과하므로 제한)
    delta = max(-45.0, min(45.0, delta))
    return int(round(90 + delta))
