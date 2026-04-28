"""
미션 상태머신 + 단순 행동 계획.
오프라인 자율 동작이므로 미션은 시작 시 코드에 주입된 웨이포인트 시퀀스를 따름.
실제 위치 추정은 IMU yaw + 시간 적분 (간단한 dead reckoning).

실서비스로 갈 때 이 모듈을 ROS 2 Nav2의 BehaviorTree + Costmap으로 대체.
"""
import enum
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

from .serial_link import SerialLink, Telemetry
from .vision import Vision, QrResult
from . import config

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    NAV_TO_BIN = "nav_to_bin"
    APPROACH = "approach"
    PICKUP = "pickup"
    NAV_TO_DEPOT = "nav_to_depot"
    DROP = "drop"
    DONE = "done"
    ABORTED = "aborted"


@dataclass
class Waypoint:
    name: str
    qr_id: Optional[str] = None       # 도착 인증용 QR (없으면 거리 기반 도달 판정)
    is_depot: bool = False


@dataclass
class Mission:
    bins: list[Waypoint]              # 방문할 빈 순서
    depot: Waypoint                   # 수거함 (시작/종료 지점)
    visited: list[str] = field(default_factory=list)


class MissionPlanner:
    """
    동작 흐름:
        IDLE → (start) → NAV_TO_BIN → APPROACH → PICKUP → NAV_TO_DEPOT → DROP → 다음 빈
        모든 빈 완료 → DONE

    단순화: 직진 + IMU yaw 보정으로 다음 빈을 향함.
            전방 < 30cm 도달 → APPROACH (저속), QR 인식 시 PICKUP.
    """

    def __init__(self, link: SerialLink, vision: Vision):
        self.link = link
        self.vision = vision
        self.state = State.IDLE
        self.mission: Optional[Mission] = None
        self.target_idx = 0
        self._state_enter_t = time.time()

    def start(self, mission: Mission):
        self.mission = mission
        self.target_idx = 0
        self._set_state(State.NAV_TO_BIN)

    def _set_state(self, s: State):
        if s != self.state:
            log.info(f"[planner] {self.state.value} → {s.value}")
            self.state = s
            self._state_enter_t = time.time()

    def _state_age(self) -> float:
        return time.time() - self._state_enter_t

    def _current_target(self) -> Optional[Waypoint]:
        if not self.mission: return None
        if self.state in (State.NAV_TO_DEPOT, State.DROP):
            return self.mission.depot
        if 0 <= self.target_idx < len(self.mission.bins):
            return self.mission.bins[self.target_idx]
        return None

    def step(self, telem: Telemetry, qrs: list[QrResult]):
        """100ms마다 호출. telem: 최신 Arduino 텔레메트리. qrs: 최신 QR 인식 결과."""
        if not telem.safe and self.state not in (State.IDLE, State.DONE, State.ABORTED):
            # 안전 트립: 잠시 후진 → 회전 → 재시도 (간단화)
            log.warning(f"[planner] safety: {telem.err}, backing up")
            self.link.move(-0.2, 0.5)   # 후진하면서 우회전
            return

        target = self._current_target()
        qr_texts = [q.text for q in qrs]

        if self.state == State.IDLE:
            self.link.stop()

        elif self.state == State.NAV_TO_BIN:
            self.link.move(config.DEFAULT_SPEED, 0.0)
            if telem.front_cm < 60:
                self._set_state(State.APPROACH)

        elif self.state == State.APPROACH:
            self.link.move(config.APPROACH_SPEED, 0.0)
            # QR 매칭 또는 30cm 이내
            if target and target.qr_id and target.qr_id in qr_texts:
                self._set_state(State.PICKUP)
            elif telem.front_cm < config.WAYPOINT_TOL_CM:
                self._set_state(State.PICKUP)
            elif self._state_age() > 5:
                log.warning("[planner] approach timeout")
                self._set_state(State.NAV_TO_BIN)

        elif self.state == State.PICKUP:
            self.link.stop()
            self.link.roller(True, 0.7)
            if self._state_age() > 3:
                self.link.roller(False)
                if self.mission and target:
                    self.mission.visited.append(target.name)
                self._set_state(State.NAV_TO_DEPOT)

        elif self.state == State.NAV_TO_DEPOT:
            self.link.move(-config.DEFAULT_SPEED, 0.0)   # 단순화: 후진
            if self._state_age() > 4:
                self._set_state(State.DROP)

        elif self.state == State.DROP:
            self.link.stop()
            self.link.roller(True, -0.7)   # 역방향 = 배출
            if self._state_age() > 3:
                self.link.roller(False)
                self.target_idx += 1
                if self.mission and self.target_idx >= len(self.mission.bins):
                    self._set_state(State.DONE)
                else:
                    self._set_state(State.NAV_TO_BIN)

        elif self.state == State.DONE:
            self.link.stop()

        elif self.state == State.ABORTED:
            self.link.stop()
