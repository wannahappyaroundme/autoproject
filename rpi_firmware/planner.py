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
from .human_guard import ObstacleGuard   # 카메라+초음파 융합 (구 HumanGuard alias 유지)
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
                 obstacle_guard: Optional[ObstacleGuard] = None,
                 human_guard: Optional[ObstacleGuard] = None):
        # human_guard는 하위 호환 인자명
        self.link = link
        self.vision = vision
        self.obstacle_guard = obstacle_guard or human_guard or ObstacleGuard()
        self.human_guard = self.obstacle_guard   # 하위 호환 alias
        self.state = State.IDLE
        self.mission: Optional[Mission] = None
        self.target_idx = 0
        self._state_enter_t = time.time()
        # WAIT_PERSON에서 장애물이 사라지면 복귀할 상태
        self._resume_state: Optional[State] = None
        # DETOUR 방향(-1=좌, +1=우). 진입 시 한 번만 결정.
        self._detour_dir: Optional[int] = None

    # ---------- 외부 API ----------

    def start(self, mission: Mission):
        self.mission = mission
        self.target_idx = 0
        self._set_state(State.NAV_TO_BIN)

    def step(self, telem: Telemetry, qrs: list[QrResult]):
        """100ms마다 호출. 최신 텔레메트리 + 최신 QR 검출 결과."""
        # 0) 측면/후방 초음파를 ObstacleGuard에 업데이트 (카메라 사각지대 보완)
        if telem.us and len(telem.us) >= 4:
            self.obstacle_guard.update_ultrasonic(
                left_cm=telem.us[1], right_cm=telem.us[2], rear_cm=telem.us[3]
            )

        # 1) Arduino 안전 트립 — 주행 상태에서만 자동 후진
        if not telem.safe and self.state in _SAFETY_TRIPABLE:
            log.warning(f"[planner] safety: {telem.err}, backing up")
            self.link.drive(-0.2)
            self.link.steer_abs(105)   # 약간 우측
            return

        # 2) 장애물 감지(카메라+초음파) 인터럽트 — 주행 중에만 적용
        if self.state in _INTERRUPTIBLE and self.obstacle_guard.is_blocked():
            reason = self.obstacle_guard.block_reason()
            log.info(f"[planner] obstacle detected ({reason}), pausing from {self.state.value}")
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
        # QR_STRICT: QR이 없으면 절대 전진 안 함. 시간 초과 시 ABORTED.
        if config.QR_STRICT and bin_target is None:
            self.link.drive(0.0)
            self.link.steer_abs(90)
            if self._state_age() > config.QR_LOSS_TIMEOUT_S:
                log.warning("[planner] NAV: QR 미감지 시간 초과 → ABORTED")
                self._set_state(State.ABORTED)
            return
        self.link.drive(config.DEFAULT_SPEED)
        self._apply_steer(bin_target)
        if telem.front_cm < config.DIST_NAV_CM:
            self._set_state(State.APPROACH)

    def _on_approach(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        if config.QR_STRICT and bin_target is None:
            self.link.drive(0.0)
            self.link.steer_abs(90)
            if self._state_age() > config.QR_LOSS_TIMEOUT_S:
                log.warning("[planner] APPROACH: QR 미감지 시간 초과 → ABORTED")
                self._set_state(State.ABORTED)
            return
        self.link.drive(config.APPROACH_SPEED)
        self._apply_steer(bin_target)
        if telem.front_cm < config.DIST_APPROACH_CM:
            self._set_state(State.ALIGN)
        elif self._state_age() > config.QR_LOSS_TIMEOUT_S:
            log.warning("[planner] APPROACH 시간 초과 → ABORTED")
            self._set_state(State.ABORTED)

    def _on_align(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 정지 상태에서 bearing 확인 → 중앙 ±deadzone 진입 시 다음 단계
        self.link.drive(0.0)
        self._apply_steer(bin_target)
        if bin_target and bin_target.centered:
            self._set_state(State.GRIP_OPEN_CONFIRM)
        elif self._state_age() > config.QR_ALIGN_TIMEOUT_S:
            if config.QR_STRICT:
                # 실물 미션: 정렬 실패는 ABORTED. 사람이 빈을 카메라 시야에 맞춰주고 재시작.
                log.warning("[planner] ALIGN: QR centering 실패 → ABORTED "
                            "(빈을 카메라 정중앙에 두고 재시작)")
                self._set_state(State.ABORTED)
            else:
                # SIMULATE dry-run: QR을 가짜로 못 만들므로 폴백 진행
                log.info("[planner] (SIMULATE) align timeout, fallback to GRIP_OPEN_CONFIRM")
                self._set_state(State.GRIP_OPEN_CONFIRM)

    def _on_grip_open_confirm(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 🛡️ 안전 가드: 빈이 충분히 가까이 와있을 때만 그리퍼 벌리기 시도.
        # 벌리는 동작 자체는 빈에 영향 없지만, 너무 멀면 무의미하게 작동 → ABORTED.
        if telem.front_cm > config.DIST_GRIP_OPEN_CM:
            log.warning(f"[planner] GRIP_OPEN: 빈 미접근 (front={telem.front_cm}cm > "
                        f"{config.DIST_GRIP_OPEN_CM}cm) → ABORTED")
            self.link.rack(0.0)
            self._set_state(State.ABORTED)
            return
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
        # 🛡️ 그리퍼 작동 진입은 매우 가까운 거리(< DIST_GRIP_CM)에서만.
        # 시간 폴백 제거 — 거리에 도달 못 하면 ABORTED (안전 우선).
        if telem.front_cm < config.DIST_GRIP_CM:
            self._set_state(State.GRIP_CLOSE)
        elif self._state_age() > config.FINAL_APPROACH_TIMEOUT_S:
            log.warning(f"[planner] FINAL_APPROACH: 도달 실패 (front={telem.front_cm}cm > "
                        f"{config.DIST_GRIP_CM}cm) → ABORTED")
            self._set_state(State.ABORTED)

    def _on_grip_close(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # 🛡️ 진입 시점에 거리 재검증 (FINAL_APPROACH에서 검증됐지만 이중 안전망).
        # 빈이 갑자기 사라졌거나 떨어진 경우(예: 누가 빈을 옮김) → 그리퍼 작동 중단.
        if telem.front_cm > config.DIST_GRIP_CM + 5:   # 약간의 마진
            log.warning(f"[planner] GRIP_CLOSE: 빈 거리 이상 (front={telem.front_cm}cm) → ABORTED")
            self.link.rack(0.0)
            self._set_state(State.ABORTED)
            return
        self.link.drive(0.0)
        if self._state_age() < config.GRIP_CLOSE_S:
            self.link.rack(+config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.LIFT)

    def _on_lift(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        # LIFT는 이미 빈을 파지한 후 시퀀스 — 거리는 매우 가까운 상태로 고정.
        # 거리 체크보다 시간만으로 운영 (빈이 들려 올라가면서 전방 초음파가 빈 본체에 막힘)
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
        if not self.obstacle_guard.is_blocked():
            # 장애물 사라짐 → 이전 상태로 복귀
            resume = self._resume_state or State.NAV_TO_BIN
            self._resume_state = None
            log.info(f"[planner] obstacle cleared, resuming {resume.value}")
            self._set_state(resume)
        elif self.obstacle_guard.should_detour():
            log.info(f"[planner] obstacle blocking >{config.PERSON_WAIT_S}s, detouring")
            self.obstacle_guard.clear()
            self._detour_dir = None   # 다음 DETOUR에서 새로 결정
            self._set_state(State.DETOUR)

    def _on_detour(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """우회 시퀀스: 후진 → 좌/우 결정 → 회전 → NAV 복귀.
        방향 결정: 좌·우 측면 초음파 비교. 차이가 DETOUR_DIR_DIFF_CM 미만이거나 헷갈리면 **우측**(사용자 지시)."""
        age = self._state_age()

        # 1) 후진 단계
        if age < config.DETOUR_BACK_S:
            self.link.drive(-0.25)
            self.link.steer_abs(90)
            return

        # 2) 방향이 아직 결정 안 됐으면 한 번만 결정
        if self._detour_dir is None:
            left_cm, right_cm = self.obstacle_guard.last_side_cm()
            # 좌측이 우측보다 DETOUR_DIR_DIFF_CM 이상 비어있으면 좌측. 그 외엔 우측 (사용자 지시).
            if left_cm > right_cm + config.DETOUR_DIR_DIFF_CM:
                self._detour_dir = -1   # 좌측
                log.info(f"[planner] DETOUR → 좌측 우회 (L={left_cm}cm, R={right_cm}cm)")
            else:
                self._detour_dir = +1   # 우측 (기본, 헷갈릴 때도)
                log.info(f"[planner] DETOUR → 우측 우회 (L={left_cm}cm, R={right_cm}cm)")

        # 3) 회전 단계 (결정된 방향)
        if age < config.DETOUR_BACK_S + config.DETOUR_TURN_S:
            self.link.drive(0.15)
            self.link.steer_abs(90 + self._detour_dir * 40)   # 좌측=-40°, 우측=+40°
        else:
            # 4) 우회 완료 → 중앙복귀 후 NAV 재진입
            self.link.steer_abs(90)
            self._resume_state = None
            self._detour_dir = None
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
