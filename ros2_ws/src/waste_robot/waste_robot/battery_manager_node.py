"""
배터리 관리 노드 — 로봇 배터리 상태를 모델링하고 퍼블리시한다.

역할:
  1. /odom 구독 → 이동 거리 기반 배터리 소모 계산
  2. 유휴 시에도 시간 기반 드레인 적용
  3. 배터리 잔량, 전압, 상태, 잔여 시간 퍼블리시
  4. ROS 2 파라미터로 임계값 설정 가능

배터리 모델:
  - 용량: 5000mAh (설정 가능)
  - 이동 소모: 0.5%/m (설정 가능)
  - 유휴 소모: 0.1%/min (설정 가능)
  - 충전 속도: 0.5%/s (설정 가능)

토픽:
  구독:
    /odom             (nav_msgs/Odometry) — 오도메트리
    /battery/command  (std_msgs/String)   — "start_charging", "stop_charging"
  발행:
    /battery/level         (std_msgs/Float32) — 잔량 (%)
    /battery/voltage       (std_msgs/Float32) — 추정 전압 (V)
    /battery/status        (std_msgs/String)  — "normal"/"low"/"critical"/"charging"
    /battery/time_remaining (std_msgs/Float32) — 잔여 시간 (분)

실행: ros2 run waste_robot battery_manager_node
"""

import math
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from nav_msgs.msg import Odometry


class BatteryManagerNode(Node):
    def __init__(self):
        super().__init__('battery_manager')

        # --- ROS 2 파라미터 ---
        self.declare_parameter('capacity_mah', 5000)
        self.declare_parameter('drain_per_meter_pct', 0.5)
        self.declare_parameter('idle_drain_per_min_pct', 0.1)
        self.declare_parameter('charge_rate_per_sec_pct', 0.5)
        self.declare_parameter('voltage_full', 12.6)
        self.declare_parameter('voltage_empty', 9.0)
        self.declare_parameter('threshold_low', 20.0)
        self.declare_parameter('threshold_critical', 10.0)
        self.declare_parameter('threshold_return', 15.0)
        self.declare_parameter('threshold_full', 95.0)
        self.declare_parameter('initial_level', 100.0)

        # --- 배터리 상태 ---
        self.level = self.get_parameter(
            'initial_level'
        ).get_parameter_value().double_value  # 잔량 (%)
        self.is_charging = False
        self.total_distance = 0.0  # 누적 이동 거리 (m)

        # 위치 추적 (이전 odom)
        self.prev_x: float | None = None
        self.prev_y: float | None = None
        self.last_drain_time = time.time()

        # --- Publishers ---
        self.level_pub = self.create_publisher(
            Float32, '/battery/level', 10
        )
        self.voltage_pub = self.create_publisher(
            Float32, '/battery/voltage', 10
        )
        self.status_pub = self.create_publisher(
            String, '/battery/status', 10
        )
        self.time_remaining_pub = self.create_publisher(
            Float32, '/battery/time_remaining', 10
        )

        # --- Subscribers ---
        self.create_subscription(
            Odometry, '/odom', self.on_odom, 10
        )
        self.create_subscription(
            String, '/battery/command', self.on_battery_command, 10
        )

        # --- 타이머 ---
        # 1초마다 배터리 상태 퍼블리시 + 유휴 드레인 적용
        self.create_timer(1.0, self.update_and_publish)

        self.get_logger().info(
            f'BatteryManagerNode 시작됨 — '
            f'초기 잔량: {self.level:.1f}%, '
            f'용량: {self.get_parameter("capacity_mah").get_parameter_value().integer_value}mAh'
        )

    # ──────────────────────────────────────────────
    # 오도메트리 콜백 — 이동 거리 기반 소모
    # ──────────────────────────────────────────────
    def on_odom(self, msg: Odometry):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        if self.prev_x is not None and self.prev_y is not None:
            dx = x - self.prev_x
            dy = y - self.prev_y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist > 0.001:  # 1mm 이상 이동 시에만
                self.total_distance += dist
                drain_pct = self.get_parameter(
                    'drain_per_meter_pct'
                ).get_parameter_value().double_value
                self.level -= dist * drain_pct
                self.level = max(0.0, self.level)

        self.prev_x = x
        self.prev_y = y

    # ──────────────────────────────────────────────
    # 배터리 명령 콜백
    # ──────────────────────────────────────────────
    def on_battery_command(self, msg: String):
        command = msg.data.strip().lower()
        if command == 'start_charging':
            self.is_charging = True
            self.get_logger().info('[배터리] 충전 시작')
        elif command == 'stop_charging':
            self.is_charging = False
            self.get_logger().info('[배터리] 충전 중지')
        elif command == 'reset':
            self.level = 100.0
            self.total_distance = 0.0
            self.get_logger().info('[배터리] 리셋: 100%')

    # ──────────────────────────────────────────────
    # 주기적 업데이트 및 퍼블리시
    # ──────────────────────────────────────────────
    def update_and_publish(self):
        now = time.time()
        elapsed_sec = now - self.last_drain_time
        self.last_drain_time = now

        if self.is_charging:
            # 충전 중
            charge_rate = self.get_parameter(
                'charge_rate_per_sec_pct'
            ).get_parameter_value().double_value
            threshold_full = self.get_parameter(
                'threshold_full'
            ).get_parameter_value().double_value
            self.level += charge_rate * elapsed_sec
            self.level = min(100.0, self.level)

            if self.level >= threshold_full:
                self.get_logger().info(
                    f'[배터리] 충전 완료: {self.level:.1f}%'
                )
        else:
            # 유휴 드레인
            idle_drain = self.get_parameter(
                'idle_drain_per_min_pct'
            ).get_parameter_value().double_value
            drain = idle_drain * (elapsed_sec / 60.0)
            self.level -= drain
            self.level = max(0.0, self.level)

        # --- 상태 결정 ---
        status = self._determine_status()

        # --- 잔여 시간 추정 ---
        time_remaining = self._estimate_time_remaining()

        # --- 전압 추정 ---
        voltage = self._estimate_voltage()

        # --- 퍼블리시 ---
        level_msg = Float32()
        level_msg.data = float(self.level)
        self.level_pub.publish(level_msg)

        voltage_msg = Float32()
        voltage_msg.data = voltage
        self.voltage_pub.publish(voltage_msg)

        status_msg = String()
        status_msg.data = status
        self.status_pub.publish(status_msg)

        time_msg = Float32()
        time_msg.data = time_remaining
        self.time_remaining_pub.publish(time_msg)

    def _determine_status(self) -> str:
        """배터리 상태 문자열 결정"""
        if self.is_charging:
            return 'charging'

        threshold_critical = self.get_parameter(
            'threshold_critical'
        ).get_parameter_value().double_value
        threshold_low = self.get_parameter(
            'threshold_low'
        ).get_parameter_value().double_value

        if self.level <= threshold_critical:
            return 'critical'
        elif self.level <= threshold_low:
            return 'low'
        return 'normal'

    def _estimate_voltage(self) -> float:
        """잔량 기반 전압 추정 (선형 모델)"""
        v_full = self.get_parameter(
            'voltage_full'
        ).get_parameter_value().double_value
        v_empty = self.get_parameter(
            'voltage_empty'
        ).get_parameter_value().double_value
        ratio = self.level / 100.0
        return v_empty + (v_full - v_empty) * ratio

    def _estimate_time_remaining(self) -> float:
        """잔여 운행 시간 추정 (분)

        유휴 드레인만 고려한 보수적 추정.
        이동 중이면 실제보다 빠르게 소모됨.
        """
        if self.is_charging:
            # 충전 완료까지 남은 시간
            threshold_full = self.get_parameter(
                'threshold_full'
            ).get_parameter_value().double_value
            charge_rate = self.get_parameter(
                'charge_rate_per_sec_pct'
            ).get_parameter_value().double_value
            remaining_pct = threshold_full - self.level
            if remaining_pct <= 0 or charge_rate <= 0:
                return 0.0
            return (remaining_pct / charge_rate) / 60.0  # 초 → 분

        idle_drain = self.get_parameter(
            'idle_drain_per_min_pct'
        ).get_parameter_value().double_value
        if idle_drain <= 0:
            return float('inf')
        return self.level / idle_drain  # 분


def main(args=None):
    rclpy.init(args=args)
    node = BatteryManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('BatteryManagerNode 종료')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
