"""
미션 상태머신 + 단순 행동 계획.

오프라인 자율 동작이므로 미션은 시작 시 코드에 주입된 웨이포인트 시퀀스를 따름.
실제 위치 추정은 IMU yaw + 시간 적분 (간단한 dead reckoning).

빈 파지 시퀀스:
  NAV_TO_BIN → APPROACH → ALIGN → GRIP_OPEN_CONFIRM → FINAL_APPROACH
    → GRIP_CLOSE → LIFT → NAV_TO_DEPOT → DROP → 다음 빈

조향: QR bbox 위치(perception.py) → 서보 P 제어.
사람 감지: 후방 웹캠 YOLO → 5초 정체 시 후진+우회전 후 같은 빈 재접근.

실서비스로 갈 때 이 모듈을 ROS 2 Nav2의 BehaviorTree + Costmap으로 대체.
"""
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .serial_link import SerialLink, Telemetry
from .vision import Vision, QrResult
from .perception import BinTarget, pick_target, steer_command_deg
from .human_guard import HumanGuard
from . import config

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    NAV_TO_BIN = "nav_to_bin"
    APPROACH = "approach"
    ALIGN = "align"
    GRIP_OPEN_CONFIRM = "grip_open_confirm"
    FINAL_APPROACH = "final_approach"
    GRIP_CLOSE = "grip_close"
    LIFT = "lift"
    NAV_TO_DEPOT = "nav_to_depot"
    DROP = "drop"
    WAIT_PERSON = "wait_person"
    DETOUR = "detour"
    DONE = "done"
    ABORTED = "aborted"


@dataclass
class Waypoint:
    name: str
    qr_id: Optional[str] = None
    is_depot: bool = False


@dataclass
class Mission:
    bins: list[Waypoint]
    depot: Waypoint
    visited: list[str] = field(default_factory=list)


# 사람 감지 인터럽트로 잠시 빠져나갔다가 복귀할 수 있는 "주행" 상태들.
# (그리퍼/롤러 시퀀스 중간에는 인터럽트하지 않음 — 빈 떨어뜨릴 위험)
_INTERRUPTIBLE = {
    State.NAV_TO_BIN,
    State.APPROACH,
    State.ALIGN,
    State.FINAL_APPROACH,
    State.NAV_TO_DEPOT,
}

# 안전 트립 시 자동 후진을 적용할 상태들(주행 중일 때만).
# 그리퍼/롤러 시퀀스 중에는 본체가 거의 정지이므로 트립이 발동하지 않음.
_SAFETY_TRIPABLE = {
    State.NAV_TO_BIN,
    State.APPROACH,
    State.ALIGN,
    State.FINAL_APPROACH,
    State.NAV_TO_DEPOT,
    State.DETOUR,
}


class MissionPlanner:
    def __init__(self, link: SerialLink, vision: Vision,
                 human_guard: Optional[HumanGuard] = None):
        self.link = link
        self.vision = vision
        self.human_guard = human_guard or HumanGuard()
        self.state = State.IDLE
        self.mission: Optional[Mission] = None
        self.target_idx = 0
        self._state_enter_t = time.time()
        # WAIT_PERSON에서 사람이 비키면 복귀할 상태
        self._resume_state: Optional[State] = None

    # ---------- 외부 API ----------

    def start(self, mission: Mission):
        self.mission = mission
        self.target_idx = 0
        self._set_state(State.NAV_TO_BIN)

    def step(self, telem: Telemetry, qrs: list[QrResult]):
        """100ms마다 호출. 최신 텔레메트리 + 최신 QR 검출 결과."""
        # 1) Arduino 안전 트립 — 주행 상태에서만 자동 후진
        if not telem.safe and self.state in _SAFETY_TRIPABLE:
            log.warning(f"[planner] safety: {telem.err}, backing up")
            self.link.drive(-0.2)
            self.link.steer_abs(105)   # 약간 우측
            return

        # 2) 사람 감지 인터럽트 — 주행 중에만 적용
        if self.state in _INTERRUPTIBLE and self.human_guard.is_blocked():
            log.info(f"[planner] person detected, pausing from {self.state.value}")
            self._resume_state = self.state
            self.link.drive(0.0)
            self.link.steer_abs(90)
            self._set_state(State.WAIT_PERSON)
            return

        # 3) 현재 target QR id
        target = self._current_target()
        target_qr_id = target.qr_id if target else None
        bin_target = pick_target(qrs, target_qr_id, telem.front_cm) if target else None

        # 4) 상태별 동작 dispatch
        handler = self._dispatch.get(self.state)
        if handler:
            handler(self, telem, bin_target)
        else:
            log.error(f"[planner] no handler for {self.state}")
            self.link.stop()

    # ---------- 내부 헬퍼 ----------

    def _set_state(self, s: State):
        if s != self.state:
            log.info(f"[planner] {self.state.value} → {s.value}")
            self.state = s
            self._state_enter_t = time.time()

    def _state_age(self) -> float:
        return time.time() - self._state_enter_t

    def _current_target(self) -> Optional[Waypoint]:
        if not self.mission:
            return None
        if self.state in (State.NAV_TO_DEPOT, State.DROP):
            return self.mission.depot
        if 0 <= self.target_idx < len(self.mission.bins):
            return self.mission.bins[self.target_idx]
        return None

    def _apply_steer(self, bin_target: Optional[BinTarget]):
        """bin_target이 있으면 P 제어로 서보 조향, 없으면 중앙(직진)."""
        if bin_target is None or not bin_target.locked:
            self.link.steer_abs(90)
            return
        deg = steer_command_deg(bin_target.bearing_deg)
        self.link.steer_abs(deg)

    # ---------- 상태 핸들러 ----------

    def _on_idle(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.stop()

    def _on_nav_to_bin(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(config.DEFAULT_SPEED)
        self._apply_steer(bin_target)
        if telem.front_cm < config.DIST_NAV_CM:
            self._set_state(State.APPROACH)

    def _on_approach(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(config.APPROACH_SPEED)
        self._apply_steer(bin_target)
        if telem.front_cm < config.DIST_APPROACH_CM:
            self._set_state(State.ALIGN)
        elif self._state_age() > 8:
            log.warning("[planner] approach timeout, retry NAV")
            self._set_state(State.NAV_TO_BIN)

    def _on_align(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 정지 상태에서 bearing 확인 → 중앙 ±deadzone 진입 시 다음 단계
        self.link.drive(0.0)
        self._apply_steer(bin_target)
        if bin_target and bin_target.centered:
            self._set_state(State.GRIP_OPEN_CONFIRM)
        elif self._state_age() > 3:
            # 3초 안에 정렬 못 했으면 QR이 가려졌거나 카메라 오류. 거리는 이미
            # APPROACH 단계를 통과한 상태이므로 거리 조건 없이 진입.
            log.info("[planner] align timeout, proceeding without QR centering")
            self._set_state(State.GRIP_OPEN_CONFIRM)

    def _on_grip_open_confirm(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 평소 벌림 상태지만 진입 시 한번 더 벌려 보장
        self.link.drive(0.0)
        self.link.steer_abs(90)
        if self._state_age() < config.GRIP_OPEN_S:
            self.link.rack(-config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.FINAL_APPROACH)

    def _on_final_approach(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(config.FINAL_APPROACH_SPEED)
        self.link.steer_abs(90)
        # ALIGN에서 정렬했으므로 직진만. 전방 ≤ 20cm 또는 1.5초 타임아웃
        if telem.front_cm < config.DIST_ALIGN_CM or self._state_age() > 1.5:
            self._set_state(State.GRIP_CLOSE)

    def _on_grip_close(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(0.0)
        if self._state_age() < config.GRIP_CLOSE_S:
            self.link.rack(+config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.LIFT)

    def _on_lift(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(0.0)
        if self._state_age() < config.LIFT_DURATION_S:
            self.link.roller(True, config.ROLLER_SPEED)
        else:
            self.link.roller(False)
            self._set_state(State.NAV_TO_DEPOT)

    def _on_nav_to_depot(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 단순화: 후진 (시제품에서는 DEPOT이 시작 지점)
        self.link.drive(-config.DEFAULT_SPEED)
        self.link.steer_abs(90)
        if self._state_age() > config.DEPOT_BACK_S:
            self._set_state(State.DROP)

    def _on_drop(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(0.0)
        age = self._state_age()
        if age < config.DROP_DURATION_S:
            # 1) 롤러 역방향 = 빈 내려놓기
            self.link.roller(True, -config.ROLLER_SPEED)
        elif age < config.DROP_DURATION_S + config.GRIP_OPEN_S:
            # 2) 그리퍼 벌림 (다음 빈을 받을 준비)
            self.link.roller(False)
            self.link.rack(-config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            if self.mission:
                visited = self.mission.bins[self.target_idx].name
                self.mission.visited.append(visited)
            self.target_idx += 1
            if self.mission and self.target_idx >= len(self.mission.bins):
                self._set_state(State.DONE)
            else:
                self._set_state(State.NAV_TO_BIN)

    def _on_wait_person(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.drive(0.0)
        self.link.steer_abs(90)
        if not self.human_guard.is_blocked():
            # 사람 사라짐 → 이전 상태로 복귀
            resume = self._resume_state or State.NAV_TO_BIN
            self._resume_state = None
            log.info(f"[planner] person cleared, resuming {resume.value}")
            self._set_state(resume)
        elif self.human_guard.should_detour():
            log.info("[planner] person blocking >5s, detouring")
            self.human_guard.clear()
            self._set_state(State.DETOUR)

    def _on_detour(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        age = self._state_age()
        if age < config.DETOUR_BACK_S:
            self.link.drive(-0.25)
            self.link.steer_abs(90)
        elif age < config.DETOUR_BACK_S + config.DETOUR_TURN_S:
            # 우회전 (서보 우측 + 저속 전진)
            self.link.drive(0.15)
            self.link.steer_abs(130)
        else:
            self.link.steer_abs(90)
            self._resume_state = None
            self._set_state(State.NAV_TO_BIN)

    def _on_done(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.stop()

    def _on_aborted(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        self.link.stop()


# 클래스 정의 후 dispatch 테이블 바인딩 (메서드 참조)
MissionPlanner._dispatch = {
    State.IDLE: MissionPlanner._on_idle,
    State.NAV_TO_BIN: MissionPlanner._on_nav_to_bin,
    State.APPROACH: MissionPlanner._on_approach,
    State.ALIGN: MissionPlanner._on_align,
    State.GRIP_OPEN_CONFIRM: MissionPlanner._on_grip_open_confirm,
    State.FINAL_APPROACH: MissionPlanner._on_final_approach,
    State.GRIP_CLOSE: MissionPlanner._on_grip_close,
    State.LIFT: MissionPlanner._on_lift,
    State.NAV_TO_DEPOT: MissionPlanner._on_nav_to_depot,
    State.DROP: MissionPlanner._on_drop,
    State.WAIT_PERSON: MissionPlanner._on_wait_person,
    State.DETOUR: MissionPlanner._on_detour,
    State.DONE: MissionPlanner._on_done,
    State.ABORTED: MissionPlanner._on_aborted,
}
