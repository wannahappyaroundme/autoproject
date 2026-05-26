"""
후방 카메라(YOLO) + 측면/후방 초음파 → "주변에 장애물이 있는가" 판단.

두 소스 융합:
  - 카메라(YOLO): 사람 + 사물 모두 검출 → 멀리서도 인지
  - 초음파(HC-SR04): 측면/후방 근접 장애물 (카메라 사각지대 보완)

블록 상태가 config.PERSON_WAIT_S 이상 지속되면 우회 필요.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import config


class ObstacleGuard:
    """카메라 + 초음파 융합 장애물 감지. 스레드 안전."""

    def __init__(self, person_wait_s: float = None):
        self._lock = threading.Lock()
        self._camera_blocked = False
        self._us_blocked = False
        self._block_start: Optional[float] = None
        self._wait_s = person_wait_s if person_wait_s is not None else config.PERSON_WAIT_S
        # DETOUR 시 좌/우 결정에 쓰일 마지막 측면 거리
        self._last_left_cm: float = 999
        self._last_right_cm: float = 999

    def update_camera(self, n_objects: int):
        """vision_loop이 매 후방 프레임마다 호출. 검출 객체 수만 받음."""
        with self._lock:
            self._camera_blocked = n_objects > 0
            self._refresh_block_start_locked()

    def update_ultrasonic(self, left_cm: float, right_cm: float, rear_cm: float):
        """planner.step()이 매 사이클 호출. 측면/후방 거리(cm) — 카메라 사각지대 보완.
        None은 미감지(매우 멀음)로 취급."""
        with self._lock:
            self._last_left_cm = left_cm if left_cm is not None else 999
            self._last_right_cm = right_cm if right_cm is not None else 999
            rear = rear_cm if rear_cm is not None else 999
            min_side = min(self._last_left_cm, self._last_right_cm)
            self._us_blocked = (
                min_side < config.OBSTACLE_SIDE_CM
                or rear < config.OBSTACLE_REAR_CM
            )
            self._refresh_block_start_locked()

    def _refresh_block_start_locked(self):
        blocked = self._camera_blocked or self._us_blocked
        if blocked and self._block_start is None:
            self._block_start = time.time()
        elif not blocked:
            self._block_start = None

    def is_blocked(self) -> bool:
        with self._lock:
            return self._camera_blocked or self._us_blocked

    def block_reason(self) -> str:
        with self._lock:
            reasons = []
            if self._camera_blocked: reasons.append("camera")
            if self._us_blocked:     reasons.append("ultrasonic")
            return "+".join(reasons) if reasons else ""

    def seconds_blocked(self) -> float:
        with self._lock:
            if self._block_start is None:
                return 0.0
            return time.time() - self._block_start

    def should_detour(self) -> bool:
        return self.seconds_blocked() >= self._wait_s

    def last_side_cm(self) -> tuple[float, float]:
        """DETOUR 방향 결정용: (좌, 우) 마지막 측면 초음파 거리."""
        with self._lock:
            return (self._last_left_cm, self._last_right_cm)

    def clear(self):
        with self._lock:
            self._camera_blocked = False
            self._us_blocked = False
            self._block_start = None


# 하위 호환 alias — 이전 코드가 HumanGuard로 import하던 곳을 안 깨기 위함
HumanGuard = ObstacleGuard
