"""
로봇 유한 상태 머신 (FSM) 노드 — 로봇의 전체 행동 상태를 관리한다.

상태 전이:
  IDLE → NAVIGATING (미션 수신)
  NAVIGATING → APPROACHING (목표 쓰레기통 1m 이내)
  APPROACHING → PICKING_UP (비주얼 서보잉으로 정렬 완료)
  PICKING_UP → RETURNING (수거 완료)
  RETURNING → DROPPING_OFF (집하장 도착)
  DROPPING_OFF → NAVIGATING (수거할 쓰레기통 남음)
  DROPPING_OFF → IDLE (미션 완료)
  ANY → EMERGENCY_STOP (초음파 < 20cm)
  EMERGENCY_STOP → 이전 상태 (장애물 해제 3초 유지)
  ANY → ERROR (센서 실패 / 타임아웃)
  NAVIGATING → NAVIGATING (경로 차단 → 재경로)
  ANY(배터리 < 15%) → RETURNING_TO_CHARGE
  RETURNING_TO_CHARGE → CHARGING (충전소 도착)
  CHARGING → IDLE (배터리 > 90%)

토픽:
  구독:
    /mission/command      (std_msgs/String)  — "start", "stop", "pause"
    /navigation/status    (std_msgs/String)  — "arrived", "blocked", "rerouting"
    /bin_detected         (std_msgs/String)  — QR/YOLO 감지 결과
    /ultrasonic/min_distance (std_msgs/Float32) — 최소 초음파 거리
    /battery/level        (std_msgs/Float32) — 배터리 잔량 (%)
  발행:
    /robot/state          (std_msgs/String)  — 현재 상태
    /navigation/goal      (geometry_msgs/PoseStamped) — 목표 위치
    /robot/error          (std_msgs/String)  — 에러 메시지

실행: ros2 run waste_robot fsm_node
"""

import json
import time
from enum import Enum

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from geometry_msgs.msg import PoseStamped


class RobotState(Enum):
    IDLE = 'IDLE'
    NAVIGATING = 'NAVIGATING'
    APPROACHING = 'APPROACHING'
    PICKING_UP = 'PICKING_UP'
    RETURNING = 'RETURNING'
    DROPPING_OFF = 'DROPPING_OFF'
    EMERGENCY_STOP = 'EMERGENCY_STOP'
    RETURNING_TO_CHARGE = 'RETURNING_TO_CHARGE'
    CHARGING = 'CHARGING'
    ERROR = 'ERROR'


class RobotFSM(Node):
    def __init__(self):
        super().__init__('robot_fsm')

        # --- ROS 2 파라미터 ---
        self.declare_parameter('emergency_distance_cm', 20.0)
        self.declare_parameter('emergency_clear_sec', 3.0)
        self.declare_parameter('battery_return_threshold', 15.0)
        self.declare_parameter('battery_full_threshold', 90.0)
        self.declare_parameter('nav_timeout_sec', 60.0)
        self.declare_parameter('comm_timeout_sec', 10.0)
        self.declare_parameter('qr_fail_max', 3)
        self.declare_parameter('charge_station_x', 0.0)
        self.declare_parameter('charge_station_y', 0.0)

        # --- 상태 ---
        self.state = RobotState.IDLE
        self.prev_state = RobotState.IDLE  # EMERGENCY_STOP 복귀용
        self.battery_level = 100.0
        self.min_distance = float('inf')  # 초음파 최소 거리 (cm)

        # 에러 복구 카운터
        self.qr_fail_count = 0
        self.nav_segment_start_time = time.time()
        self.last_comm_time = time.time()
        self.emergency_clear_start = None  # 장애물 해제 타이머

        # 미션 데이터
        self.remaining_bins = 0  # 남은 수거 쓰레기통 수
        self.paused = False

        # --- Publishers ---
        self.state_pub = self.create_publisher(String, '/robot/state', 10)
        self.goal_pub = self.create_publisher(
            PoseStamped, '/navigation/goal', 10
        )
        self.error_pub = self.create_publisher(String, '/robot/error', 10)

        # --- Subscribers ---
        self.create_subscription(
            String, '/mission/command', self.on_mission_command, 10
        )
        self.create_subscription(
            String, '/navigation/status', self.on_navigation_status, 10
        )
        self.create_subscription(
            String, '/bin_detected', self.on_bin_detected, 10
        )
        self.create_subscription(
            Float32, '/ultrasonic/min_distance', self.on_ultrasonic, 10
        )
        self.create_subscription(
            Float32, '/battery/level', self.on_battery_level, 10
        )

        # --- 타이머 ---
        # 상태 퍼블리시 (1초)
        self.create_timer(1.0, self.publish_state)
        # 타임아웃/에러 감시 (0.5초)
        self.create_timer(0.5, self.check_timeouts)

        self.get_logger().info('RobotFSM 시작됨 — 상태: IDLE')

    # ──────────────────────────────────────────────
    # 상태 전이 헬퍼
    # ──────────────────────────────────────────────
    def transition_to(self, new_state: RobotState, reason: str = ''):
        old_state = self.state
        if old_state == new_state:
            return
        self.state = new_state
        ts = self.get_clock().now().nanoseconds / 1e9
        self.get_logger().info(
            f'[FSM] {old_state.value} → {new_state.value} '
            f'(reason: {reason}) @ t={ts:.2f}'
        )
        # 네비게이션 세그먼트 타이머 리셋
        if new_state == RobotState.NAVIGATING:
            self.nav_segment_start_time = time.time()

    def publish_error(self, message: str):
        msg = String()
        msg.data = message
        self.error_pub.publish(msg)
        self.get_logger().error(f'[FSM ERROR] {message}')

    # ──────────────────────────────────────────────
    # 콜백: 미션 명령
    # ──────────────────────────────────────────────
    def on_mission_command(self, msg: String):
        command = msg.data.strip().lower()
        self.last_comm_time = time.time()

        if command == 'start':
            if self.state == RobotState.IDLE:
                self.qr_fail_count = 0
                self.transition_to(RobotState.NAVIGATING, '미션 시작')
            else:
                self.get_logger().warn(
                    f'미션 시작 무시 — 현재 상태: {self.state.value}'
                )

        elif command == 'stop':
            self.transition_to(RobotState.IDLE, '미션 중지 명령')

        elif command == 'pause':
            if self.state not in (RobotState.IDLE, RobotState.ERROR,
                                  RobotState.EMERGENCY_STOP,
                                  RobotState.CHARGING):
                self.paused = True
                self.get_logger().info('[FSM] 일시정지')

        elif command == 'resume':
            if self.paused:
                self.paused = False
                self.get_logger().info('[FSM] 재개')

    # ──────────────────────────────────────────────
    # 콜백: 네비게이션 상태
    # ──────────────────────────────────────────────
    def on_navigation_status(self, msg: String):
        status = msg.data.strip().lower()
        self.last_comm_time = time.time()

        if self.paused:
            return

        if status == 'arrived':
            self._handle_arrival()
        elif status == 'blocked':
            if self.state == RobotState.NAVIGATING:
                self.get_logger().warn('[FSM] 경로 차단 — 재경로 요청')
                self.transition_to(
                    RobotState.NAVIGATING, '경로 차단 → 재경로'
                )
        elif status == 'rerouting':
            self.get_logger().info('[FSM] 재경로 진행 중')
        elif status == 'near_target':
            if self.state == RobotState.NAVIGATING:
                self.transition_to(
                    RobotState.APPROACHING, '목표 1m 이내 접근'
                )

    def _handle_arrival(self):
        if self.state == RobotState.APPROACHING:
            self.transition_to(
                RobotState.PICKING_UP, '쓰레기통 정렬 완료'
            )
        elif self.state == RobotState.PICKING_UP:
            self.transition_to(
                RobotState.RETURNING, '수거 완료 → 집하장 복귀'
            )
        elif self.state in (RobotState.RETURNING, RobotState.NAVIGATING):
            self.transition_to(RobotState.DROPPING_OFF, '집하장 도착')
        elif self.state == RobotState.DROPPING_OFF:
            self.remaining_bins -= 1
            if self.remaining_bins > 0:
                self.transition_to(
                    RobotState.NAVIGATING, '다음 쓰레기통으로 이동'
                )
            else:
                self.transition_to(RobotState.IDLE, '미션 완료')
        elif self.state == RobotState.RETURNING_TO_CHARGE:
            self.transition_to(RobotState.CHARGING, '충전소 도착')

    # ──────────────────────────────────────────────
    # 콜백: QR/YOLO 감지
    # ──────────────────────────────────────────────
    def on_bin_detected(self, msg: String):
        self.last_comm_time = time.time()

        try:
            data = json.loads(msg.data)
        except Exception:
            data = {'method': 'unknown', 'result': msg.data}

        method = data.get('method', 'unknown')
        success = data.get('success', False)

        if self.state == RobotState.APPROACHING:
            if success:
                self.qr_fail_count = 0
                self.get_logger().info(
                    f'[FSM] 쓰레기통 감지 성공 (방법: {method})'
                )
            else:
                if method == 'qr':
                    self.qr_fail_count += 1
                    max_fail = self.get_parameter(
                        'qr_fail_max'
                    ).get_parameter_value().integer_value
                    if self.qr_fail_count >= max_fail:
                        self.get_logger().warn(
                            f'[FSM] QR 감지 {self.qr_fail_count}회 실패 '
                            f'→ YOLO 폴백 전환'
                        )
                        # YOLO 폴백은 외부 비전 노드에서 처리;
                        # 여기서는 카운터 리셋
                        self.qr_fail_count = 0

    # ──────────────────────────────────────────────
    # 콜백: 초음파 센서
    # ──────────────────────────────────────────────
    def on_ultrasonic(self, msg: Float32):
        self.min_distance = msg.data
        self.last_comm_time = time.time()
        emergency_dist = self.get_parameter(
            'emergency_distance_cm'
        ).get_parameter_value().double_value

        if msg.data < emergency_dist:
            # 긴급 정지
            if self.state != RobotState.EMERGENCY_STOP:
                self.prev_state = self.state
                self.transition_to(
                    RobotState.EMERGENCY_STOP,
                    f'초음파 {msg.data:.1f}cm < {emergency_dist:.0f}cm'
                )
            self.emergency_clear_start = None  # 장애물 아직 있음
        else:
            # 장애물 해제 감지
            if self.state == RobotState.EMERGENCY_STOP:
                if self.emergency_clear_start is None:
                    self.emergency_clear_start = time.time()
                clear_sec = self.get_parameter(
                    'emergency_clear_sec'
                ).get_parameter_value().double_value
                elapsed = time.time() - self.emergency_clear_start
                if elapsed >= clear_sec:
                    self.transition_to(
                        self.prev_state,
                        f'장애물 해제 {clear_sec:.0f}초 경과 → 복귀'
                    )
                    self.emergency_clear_start = None

    # ──────────────────────────────────────────────
    # 콜백: 배터리
    # ──────────────────────────────────────────────
    def on_battery_level(self, msg: Float32):
        self.battery_level = msg.data
        self.last_comm_time = time.time()

        battery_return = self.get_parameter(
            'battery_return_threshold'
        ).get_parameter_value().double_value
        battery_full = self.get_parameter(
            'battery_full_threshold'
        ).get_parameter_value().double_value

        # 저배터리 → 충전소 복귀
        if (msg.data < battery_return
                and self.state not in (
                    RobotState.RETURNING_TO_CHARGE,
                    RobotState.CHARGING,
                    RobotState.IDLE,
                    RobotState.ERROR,
                    RobotState.EMERGENCY_STOP,
                )):
            self.transition_to(
                RobotState.RETURNING_TO_CHARGE,
                f'배터리 {msg.data:.1f}% < {battery_return:.0f}%'
            )
            self._send_charge_station_goal()

        # 충전 완료
        if self.state == RobotState.CHARGING and msg.data >= battery_full:
            self.transition_to(
                RobotState.IDLE,
                f'충전 완료 — 배터리 {msg.data:.1f}%'
            )

    def _send_charge_station_goal(self):
        x = self.get_parameter(
            'charge_station_x'
        ).get_parameter_value().double_value
        y = self.get_parameter(
            'charge_station_y'
        ).get_parameter_value().double_value
        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = x
        goal.pose.position.y = y
        self.goal_pub.publish(goal)
        self.get_logger().info(f'[FSM] 충전소 목표 전송: ({x}, {y})')

    # ──────────────────────────────────────────────
    # 주기적 감시: 타임아웃 / 에러
    # ──────────────────────────────────────────────
    def check_timeouts(self):
        now = time.time()

        # 네비게이션 세그먼트 타임아웃
        if self.state == RobotState.NAVIGATING:
            nav_timeout = self.get_parameter(
                'nav_timeout_sec'
            ).get_parameter_value().double_value
            if now - self.nav_segment_start_time > nav_timeout:
                self.get_logger().warn(
                    f'[FSM] 네비게이션 타임아웃 '
                    f'({nav_timeout:.0f}s) → 재경로'
                )
                self.nav_segment_start_time = now
                self.publish_error(
                    f'네비게이션 타임아웃 {nav_timeout:.0f}s'
                )

        # 통신 타임아웃 (IDLE, CHARGING 제외)
        if self.state not in (RobotState.IDLE, RobotState.CHARGING,
                              RobotState.ERROR):
            comm_timeout = self.get_parameter(
                'comm_timeout_sec'
            ).get_parameter_value().double_value
            if now - self.last_comm_time > comm_timeout:
                self.get_logger().warn(
                    f'[FSM] 통신 타임아웃 ({comm_timeout:.0f}s) '
                    '→ 로컬 자율 모드'
                )
                self.publish_error(
                    '통신 타임아웃 — 로컬 자율 모드 전환'
                )
                self.last_comm_time = now  # 반복 경고 방지

    # ──────────────────────────────────────────────
    # 상태 퍼블리시
    # ──────────────────────────────────────────────
    def publish_state(self):
        msg = String()
        msg.data = self.state.value
        self.state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RobotFSM()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('RobotFSM 종료')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
