"""
후방 웹캠 → YOLO person 검출 → "사람이 길을 막고 있는가" 판단.

스레드 안전. vision_loop(rear)이 매 프레임 update(persons)를 호출하고,
planner.step()은 is_blocked()로 즉시 조회.

블록 시간(seconds_blocked)이 config.PERSON_WAIT_S 이상 → 우회로 판단.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import config


class HumanGuard:
    def __init__(self, person_wait_s: float = None):
        self._lock = threading.Lock()
        self._blocked = False
        self._block_start: Optional[float] = None
        self._wait_s = person_wait_s if person_wait_s is not None else config.PERSON_WAIT_S

    def update(self, n_persons: int):
        """매 후방 프레임마다 호출. person 검출 개수만 받음."""
        now = time.time()
        with self._lock:
            if n_persons > 0:
                if not self._blocked:
                    self._blocked = True
                    self._block_start = now
            else:
                self._blocked = False
                self._block_start = None

    def is_blocked(self) -> bool:
        with self._lock:
            return self._blocked

    def seconds_blocked(self) -> float:
        with self._lock:
            if self._blocked and self._block_start is not None:
                return time.time() - self._block_start
            return 0.0

    def should_detour(self) -> bool:
        """블록된 채 PERSON_WAIT_S 이상 → 우회 필요."""
        return self.seconds_blocked() >= self._wait_s

    def clear(self):
        with self._lock:
            self._blocked = False
            self._block_start = None
