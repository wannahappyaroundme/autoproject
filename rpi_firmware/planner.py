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
    BLIND_PUSH = "blind_push"            # 🆕 QR 잃었지만 가까이 와있음 → 마지막 본 서보각으로 2초 직진
    GRIP_OPEN_CONFIRM = "grip_open_confirm"
    FINAL_APPROACH = "final_approach"
    # 🆕 반자동(semi-auto) 모드 — 자율은 여기까지, 그 후 사용자 수동 트리거 대기
    STANDBY = "standby"                       # 자동 정지, 페이지 버튼 입력 대기
    MANUAL_GRIP_CLOSE = "manual_grip_close"   # 그리퍼 모음 (트리거)
    MANUAL_GRIP_OPEN = "manual_grip_open"     # 그리퍼 벌리기 (트리거)
    MANUAL_LIFT = "manual_lift"               # 롤러 정방향 (트리거)
    MANUAL_DROP = "manual_drop"               # 롤러 역방향 + 그리퍼 벌리기 시퀀스
    MANUAL_REVERSE = "manual_reverse"         # 후진 (트리거)
    # 기존 완전자동 단계 (호환 유지, 현재 자동 흐름에선 안 씀)
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
# BLIND_PUSH는 짧고(2초) QR 없이 마지막 방향으로 가는 단계라 인터럽트 X — 한번 시작하면 끝까지.
_INTERRUPTIBLE = {
    State.NAV_TO_BIN,
    State.APPROACH,
    State.ALIGN,
    State.FINAL_APPROACH,
    State.NAV_TO_DEPOT,
}

# 안전 트립 시 자동 후진을 적용할 상태들(주행 중일 때만).
# 그리퍼/롤러 시퀀스 중에는 본체가 거의 정지이므로 트립이 발동하지 않음.
# BLIND_PUSH도 안전 트립은 적용 (전방 15cm 충돌 방지).
_SAFETY_TRIPABLE = {
    State.NAV_TO_BIN,
    State.APPROACH,
    State.ALIGN,
    State.BLIND_PUSH,
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
        # 🆕 BLIND_PUSH용 — 마지막으로 QR을 본 시각 + 그때 적용한 서보 각.
        # QR이 가까이서 깨졌을 때 이 정보로 마지막 방향으로 직진.
        self._last_qr_seen_t: float = 0.0
        self._last_steer_deg: int = 90   # 90 = 중앙(직진)

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

        # 🆕 QR 본 시각 + 마지막 조향각 기록 (BLIND_PUSH에서 사용).
        # bin_target.locked = QR이 충분히 안정적으로 잡힌 상태.
        if bin_target and bin_target.locked:
            self._last_qr_seen_t = time.time()
            self._last_steer_deg = steer_command_deg(bin_target.bearing_deg)

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

    def _qr_lost_duration(self) -> float:
        """마지막으로 QR을 안정적으로 본 시점부터 경과 시간(초). 한 번도 못 봤으면 큰 값."""
        if self._last_qr_seen_t <= 0:
            return 999.0
        return time.time() - self._last_qr_seen_t

    def _should_blind_push(self, telem: Telemetry, bin_target: Optional[BinTarget]) -> bool:
        """QR이 가까이서 깨졌을 때 BLIND_PUSH로 전환할지 판단.
        조건: 현재 QR 없음 + 마지막으로 QR 본 적 있음 + 가까이 와있음 + 깜빡임 아닌 진짜 lost."""
        return (
            bin_target is None
            and self._last_qr_seen_t > 0
            and telem.front_cm < config.BLIND_PUSH_TRIGGER_CM
            and self._qr_lost_duration() > config.BLIND_PUSH_QR_LOST_S
        )

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
        # 🆕 가까이 왔는데 QR 깨짐 → BLIND_PUSH로 우회 (정지하지 말고 마지막 방향으로 직진)
        if config.QR_STRICT and self._should_blind_push(telem, bin_target):
            log.info(f"[planner] APPROACH: QR lost {self._qr_lost_duration():.1f}s "
                     f"at {telem.front_cm}cm → BLIND_PUSH")
            self._set_state(State.BLIND_PUSH)
            return

        # 멀리서 QR 없음 → 정지 + timeout (기존 동작)
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
        """🔧 재설계: QR이 잡히는 동안 계속 전진 + 조향. QR 끊기면 BLIND_PUSH로 4초 더 들어감.
        (정지 상태로는 bearing이 안 바뀌므로 정렬 불가능 — 차가 움직여야 카메라 시야에서 빈이 좌우 이동)
        종료 조건 (우선순위 순):
          1) QR 끊김 (가까이서) → BLIND_PUSH ★ 사용자 의도 핵심 경로
          2) centered (deadzone 진입) → GRIP_OPEN_CONFIRM
          3) 시간 초과 → 가까우면 BLIND_PUSH, 멀면 ABORTED
        ⚠️ DIST_ALIGN_CM 거리 자동 진입 제거 — QR 끊길 때까지 계속 추적해야 BLIND_PUSH 흐름 살아남.
        충돌 방지는 Arduino 전방 15cm 자동 안전 트립(_SAFETY_TRIPABLE)이 담당.
        """
        # 1) QR 가까이서 깨졌으면 즉시 BLIND_PUSH (사용자 의도 핵심 경로)
        if config.QR_STRICT and self._should_blind_push(telem, bin_target):
            log.info(f"[planner] ALIGN: QR lost {self._qr_lost_duration():.1f}s "
                     f"at {telem.front_cm}cm → BLIND_PUSH ({config.BLIND_PUSH_DURATION_S}s 전진)")
            self._set_state(State.BLIND_PUSH)
            return

        # 전진 + 조향 (정중앙 추적)
        self.link.drive(config.ALIGN_DRIVE_SPEED)
        self._apply_steer(bin_target)

        # 2) 중앙 정렬됨 → 정상 진행
        if bin_target and bin_target.centered:
            log.info(f"[planner] ALIGN: centered → GRIP_OPEN")
            self.link.drive(0.0)
            self._set_state(State.GRIP_OPEN_CONFIRM)
            return

        # 3) 시간 초과
        if self._state_age() > config.QR_ALIGN_TIMEOUT_S:
            if config.QR_STRICT:
                # 가까이 와있으면 BLIND_PUSH로 우회
                if telem.front_cm < config.BLIND_PUSH_TRIGGER_CM:
                    log.info(f"[planner] ALIGN: timeout at {telem.front_cm}cm → BLIND_PUSH")
                    self._set_state(State.BLIND_PUSH)
                    return
                log.warning("[planner] ALIGN: QR centering 실패 → ABORTED "
                            "(빈을 카메라 정중앙에 두고 재시작)")
                self._set_state(State.ABORTED)
            else:
                log.info("[planner] (SIMULATE) align timeout, fallback to GRIP_OPEN_CONFIRM")
                self._set_state(State.GRIP_OPEN_CONFIRM)

    def _on_blind_push(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """🆕 QR이 가까이서 깨졌을 때 — 마지막 본 서보 각으로 BLIND_PUSH_DURATION_S(2초) 직진.
        빈이 카메라 시야 사각지대로 들어간 케이스 (너무 가까워 QR finder pattern 인식 불가).
        2초 후 STANDBY 진입 → 사용자가 페이지에서 그리퍼 트리거.
        도중 QR이 다시 보이면 ALIGN으로 복귀 (운 좋게 시야 회복 케이스)."""
        # 도중 QR 다시 보임 → ALIGN으로 (정렬 한 번 더)
        if bin_target and bin_target.locked:
            log.info(f"[planner] BLIND_PUSH: QR 다시 잡힘 → ALIGN")
            self._set_state(State.ALIGN)
            return

        if self._state_age() < config.BLIND_PUSH_DURATION_S:
            self.link.drive(config.BLIND_PUSH_SPEED)
            self.link.steer_abs(self._last_steer_deg)
        else:
            self.link.drive(0.0)
            self.link.steer_abs(90)
            log.info(f"[planner] BLIND_PUSH 완료 (front={telem.front_cm}cm, "
                     f"last_steer={self._last_steer_deg}°) → STANDBY")
            self._set_state(State.STANDBY)

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
        # 반자동 모드: 도달 시 자동 그리퍼 작동 X. STANDBY 진입 → 페이지 버튼으로 사용자 직접 트리거.
        if telem.front_cm < config.DIST_GRIP_CM:
            log.info(f"[planner] FINAL_APPROACH 완료 (front={telem.front_cm}cm) → STANDBY "
                     f"(페이지에서 그리퍼/롤러 수동 트리거)")
            self.link.drive(0.0)
            self._set_state(State.STANDBY)
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

    # ---------- 🆕 반자동(semi-auto) 핸들러 ----------

    def _on_standby(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """페이지 입력 대기. 진입 직후만 안전 초기화, 이후엔 사용자 수동 명령 통과.
        매 step마다 drive(0) 보내면 사용자 hold-button을 덮어쓰므로 한 번만."""
        if self._state_age() < 0.2:
            # 진입 직후: 모든 모터 정지 + 서보 중앙 + 롤러 OFF. rack은 마지막 위치 유지.
            self.link.drive(0.0)
            self.link.steer_abs(90)
            self.link.rack(0.0)
            self.link.roller(False)
        # 이후: 아무 명령도 안 보냄 → 사용자의 수동 명령(/api/manual_*)이 link에 직접 전달.
        # 사용자가 명령 안 보내면 Arduino watchdog(500ms)이 알아서 정지.

    def _on_manual_grip_close(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """🤝 사용자 트리거 — 그리퍼 모음(파지). 일정 시간 후 STANDBY 복귀."""
        # 🛡️ 안전 가드: 거리 너무 멀면 즉시 STANDBY (그리퍼 작동 X)
        if telem.front_cm > config.DIST_GRIP_CM + 8:
            log.warning(f"[planner] MANUAL_GRIP_CLOSE: 거리 너무 멀음 ({telem.front_cm}cm) → 취소")
            self.link.rack(0.0)
            self._set_state(State.STANDBY)
            return
        self.link.drive(0.0)
        if self._state_age() < config.GRIP_CLOSE_S:
            self.link.rack(+config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.STANDBY)

    def _on_manual_grip_open(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """그리퍼 벌리기 (해제). 거리 가드 없음 — 빈 떨어뜨리기 안전 동작."""
        self.link.drive(0.0)
        if self._state_age() < config.GRIP_OPEN_S:
            self.link.rack(-config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.STANDBY)

    def _on_manual_lift(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """🔃 롤러 정방향 — 빈 들어올림. 시간 후 STANDBY."""
        self.link.drive(0.0)
        if self._state_age() < config.LIFT_DURATION_S:
            self.link.roller(True, config.ROLLER_SPEED)
        else:
            self.link.roller(False)
            self._set_state(State.STANDBY)

    def _on_manual_drop(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """⬇ 롤러 역방향(배출) → 그리퍼 벌리기 → STANDBY."""
        self.link.drive(0.0)
        age = self._state_age()
        if age < config.DROP_DURATION_S:
            self.link.roller(True, -config.ROLLER_SPEED)
        elif age < config.DROP_DURATION_S + config.GRIP_OPEN_S:
            self.link.roller(False)
            self.link.rack(-config.GRIP_SPEED)
        else:
            self.link.rack(0.0)
            self._set_state(State.STANDBY)

    def _on_manual_reverse(self, telem: Telemetry, bin_target: Optional[BinTarget]):
        """↩ 후진 시퀀스. 시간 후 STANDBY."""
        if self._state_age() < config.DETOUR_BACK_S:
            self.link.drive(-0.15)
            self.link.steer_abs(90)
        else:
            self.link.drive(0.0)
            self._set_state(State.STANDBY)

    # ---------- 외부 트리거 (페이지 버튼이 호출) ----------

    def trigger_start(self, mission: Mission) -> bool:
        """미션 시작. IDLE/DONE/ABORTED 상태에서만 허용."""
        if self.state in (State.IDLE, State.DONE, State.ABORTED):
            self.start(mission)
            return True
        log.warning(f"[planner] trigger_start 무시: 현재 {self.state.value}")
        return False

    def trigger_grip_close(self) -> bool:
        if self.state == State.STANDBY:
            self._set_state(State.MANUAL_GRIP_CLOSE)
            return True
        return False

    def trigger_grip_open(self) -> bool:
        if self.state == State.STANDBY:
            self._set_state(State.MANUAL_GRIP_OPEN)
            return True
        return False

    def trigger_lift(self) -> bool:
        if self.state == State.STANDBY:
            self._set_state(State.MANUAL_LIFT)
            return True
        return False

    def trigger_drop(self) -> bool:
        if self.state == State.STANDBY:
            self._set_state(State.MANUAL_DROP)
            return True
        return False

    def trigger_reverse(self) -> bool:
        if self.state == State.STANDBY:
            self._set_state(State.MANUAL_REVERSE)
            return True
        return False

    # 🆕 hold-button 형식 수동 조작 (STANDBY에서만, 그리퍼/롤러 상태는 유지)
    def trigger_manual_drive(self, speed: float) -> bool:
        """전후진. speed: -0.20 ~ +0.20. Arduino watchdog가 500ms 내 명령 없으면 자동 정지."""
        if self.state == State.STANDBY:
            self.link.drive(float(speed))
            return True
        return False

    def trigger_manual_steer(self, direction: int) -> bool:
        """서보 점진 회전. direction: +1=우, -1=좌, 0=중앙복귀. 펌웨어가 점진 ramping."""
        if self.state == State.STANDBY:
            self.link.steer(float(direction))
            return True
        return False

    def reset_to_idle(self):
        """언제든 호출 가능 — 모든 모터 정지 + 미션 상태 초기화."""
        self.link.drive(0.0)
        self.link.rack(0.0)
        self.link.roller(False)
        self.link.steer_abs(90)
        self._resume_state = None
        self._detour_dir = None
        self.target_idx = 0
        self._set_state(State.IDLE)


# 클래스 정의 후 dispatch 테이블 바인딩 (메서드 참조)
MissionPlanner._dispatch = {
    State.IDLE: MissionPlanner._on_idle,
    State.NAV_TO_BIN: MissionPlanner._on_nav_to_bin,
    State.APPROACH: MissionPlanner._on_approach,
    State.ALIGN: MissionPlanner._on_align,
    State.BLIND_PUSH: MissionPlanner._on_blind_push,
    State.GRIP_OPEN_CONFIRM: MissionPlanner._on_grip_open_confirm,
    State.FINAL_APPROACH: MissionPlanner._on_final_approach,
    # 반자동
    State.STANDBY: MissionPlanner._on_standby,
    State.MANUAL_GRIP_CLOSE: MissionPlanner._on_manual_grip_close,
    State.MANUAL_GRIP_OPEN: MissionPlanner._on_manual_grip_open,
    State.MANUAL_LIFT: MissionPlanner._on_manual_lift,
    State.MANUAL_DROP: MissionPlanner._on_manual_drop,
    State.MANUAL_REVERSE: MissionPlanner._on_manual_reverse,
    # 기존 완전자동 (호환 유지)
    State.GRIP_CLOSE: MissionPlanner._on_grip_close,
    State.LIFT: MissionPlanner._on_lift,
    State.NAV_TO_DEPOT: MissionPlanner._on_nav_to_depot,
    State.DROP: MissionPlanner._on_drop,
    State.WAIT_PERSON: MissionPlanner._on_wait_person,
    State.DETOUR: MissionPlanner._on_detour,
    State.DONE: MissionPlanner._on_done,
    State.ABORTED: MissionPlanner._on_aborted,
}
