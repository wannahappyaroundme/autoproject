"""
안전 관리 노드 — 비상정지, 배터리 관리, 통신 실패 대응을 담당한다.

하드웨어 명세서 Section 10.4 (비상정지 로직) 구현:

초음파 기반 비상정지 거리:
  | 센서          | 비상정지 | 감속    |
  | FL (전방좌)   | < 20cm   | < 50cm  |
  | FR (전방우)   | < 20cm   | < 50cm  |
  | SL (측면좌)   | < 15cm   | < 30cm  |
  | SR (측면우)   | < 15cm   | < 30cm  |
  | R  (후방)     | < 30cm   | < 80cm  |

배터리 관리:
  - < 20%: 미션 중단 → 집하장 자동 복귀
  - < 10%: 현재 위치에서 즉시 정지 + 관제 알림

통신 실패 대응:
  - WiFi/MQTT 끊김 3초: 현재 위치 정지 → 재연결 대기
  - 30초 재연결 실패: 집하장 자동 복귀 (오프라인 모드)

네비게이션 실패 대응:
  - Nav2 실패 1회: 후진 0.5m → 재시도
  - 3회 연속 실패: 정지 + 관제 알림 + 수동 개입 대기

토픽:
  - /ultrasonic/ranges (sub)   : 초음파 5개 거리 데이터
  - /battery/state (sub)       : 배터리 전압/잔량
  - /mqtt/status (sub)         : MQTT 연결 상태
  - /navigation/result (sub)   : 네비게이션 결과
  - /cmd_vel (pub)             : 비상정지 시 속도 0
  - /safety/status (pub)       : 안전 상태 보고
  - /safety/estop (pub)        : 비상정지 발생 이벤트
  - /mission/command (pub)     : 미션 중단 명령

실행: ros2 run waste_robot safety_manager
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist


class SafetyManager(Node):
    """
    다층 안전 시스템

    우선순위:
      1. 비상정지 (초음파) — 즉시 반응
      2. 배터리 부족 — 미션 수준 대응
      3. 통신 실패 — 점진적 대응
      4. 네비게이션 실패 — 재시도 + 에스컬레이션
    """

    # 초음파 비상정지/감속 거리 (cm) — 하드웨어 명세서 기준
    US_THRESHOLDS = {
        'us_front_left':  {'estop': 20, 'slow': 50},
        'us_front_right': {'estop': 20, 'slow': 50},
        'us_side_left':   {'estop': 15, 'slow': 30},
        'us_side_right':  {'estop': 15, 'slow': 30},
        'us_rear':        {'estop': 30, 'slow': 80},
    }

    def __init__(self):
        super().__init__('safety_manager')

        # --- 파라미터 ---
        self.declare_parameter('battery_low_pct', 20.0)
        self.declare_parameter('battery_critical_pct', 10.0)
        self.declare_parameter('comm_timeout_sec', 3.0)
        self.declare_parameter('comm_offline_timeout_sec', 30.0)
        self.declare_parameter('nav_max_retries', 3)
        self.declare_parameter('estop_hold_sec', 3.0)

        # --- Publishers ---
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.status_pub = self.create_publisher(String, '/safety/status', 10)
        self.estop_pub = self.create_publisher(Bool, '/safety/estop', 10)
        self.mission_cmd_pub = self.create_publisher(String, '/mission/command', 10)

        # --- Subscribers ---
        self.us_sub = self.create_subscription(
            String, '/ultrasonic/ranges', self.on_ultrasonic, 10
        )
        self.battery_sub = self.create_subscription(
            String, '/battery/state', self.on_battery, 10
        )
        self.mqtt_sub = self.create_subscription(
            String, '/mqtt/status', self.on_mqtt_status, 10
        )
        self.nav_result_sub = self.create_subscription(
            String, '/navigation/result', self.on_nav_result, 10
        )
        self.mode_sub = self.create_subscription(
            String, '/robot/mode', self.on_mode, 10
        )

        # --- 상태 ---
        self.estop_active = False
        self.speed_limit = 1.0        # 1.0 = 정상, 0.5 = 감속, 0.0 = 정지
        self.battery_pct = 100.0
        self.battery_voltage = 12.6
        self.mqtt_connected = True
        self.mqtt_last_seen = 0.0
        self.nav_fail_count = 0
        self.current_mode = 'B'
        self.estop_start_time = 0.0
        self.us_distances = {}        # 최신 초음파 데이터

        # 50Hz 안전 체크 (20ms)
        self.timer = self.create_timer(0.02, self.safety_check)
        # 1초마다 상태 보고
        self.report_timer = self.create_timer(1.0, self.report_status)

        self.get_logger().info('SafetyManager 시작됨')
        self.get_logger().info(f'  비상정지 거리: 전방 20cm, 측면 15cm, 후방 30cm')

    def on_mode(self, msg: String):
        self.current_mode = msg.data.upper()

    def on_ultrasonic(self, msg: String):
        """초음파 데이터 수신 (JSON: {sensor_name: distance_cm, ...})"""
        try:
            self.us_distances = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def on_battery(self, msg: String):
        """배터리 상태 수신"""
        try:
            data = json.loads(msg.data)
            self.battery_pct = data.get('percentage', 100.0)
            self.battery_voltage = data.get('voltage', 12.6)
        except json.JSONDecodeError:
            # DATA,BAT,voltage 형태일 수도 있음
            parts = msg.data.split(',')
            if len(parts) >= 3 and parts[0] == 'DATA' and parts[1] == 'BAT':
                self.battery_voltage = float(parts[2])
                # 11.1V(3S 최저) ~ 12.6V(만충) → 백분율
                self.battery_pct = max(0, min(100,
                    (self.battery_voltage - 11.1) / (12.6 - 11.1) * 100
                ))

    def on_mqtt_status(self, msg: String):
        """MQTT 연결 상태"""
        self.mqtt_connected = msg.data.lower() == 'connected'
        if self.mqtt_connected:
            self.mqtt_last_seen = self.get_clock().now().nanoseconds * 1e-9

    def on_nav_result(self, msg: String):
        """네비게이션 결과"""
        if msg.data == 'arrived':
            self.nav_fail_count = 0
        elif msg.data == 'failed':
            self.nav_fail_count += 1
            max_retries = int(self.get_parameter('nav_max_retries').value)
            self.get_logger().warn(
                f'네비게이션 실패 ({self.nav_fail_count}/{max_retries})'
            )
            if self.nav_fail_count >= max_retries:
                self.get_logger().error('3회 연속 네비게이션 실패 — 정지 + 관제 알림')
                self.emergency_stop('nav_failure_3x')

    def safety_check(self):
        """50Hz 안전 체크 메인 루프"""
        now = self.get_clock().now().nanoseconds * 1e-9

        # === 1. 초음파 비상정지 체크 (최우선) ===
        estop_triggered = False
        slow_triggered = False

        for sensor_name, thresholds in self.US_THRESHOLDS.items():
            dist_cm = self.us_distances.get(sensor_name, 999)

            # 모드에 따라 전방/후방 센서 우선순위 변경
            if self.current_mode == 'A':
                # 모드 A: 전방 센서가 중요
                if sensor_name.startswith('us_front') and dist_cm < thresholds['estop']:
                    estop_triggered = True
                elif sensor_name.startswith('us_front') and dist_cm < thresholds['slow']:
                    slow_triggered = True
            else:
                # 모드 B: 후방 센서가 중요 (후진 방향)
                if sensor_name == 'us_rear' and dist_cm < thresholds['estop']:
                    estop_triggered = True
                elif sensor_name == 'us_rear' and dist_cm < thresholds['slow']:
                    slow_triggered = True

            # 측면 센서는 양 모드 공통
            if sensor_name.startswith('us_side') and dist_cm < thresholds['estop']:
                estop_triggered = True
            elif sensor_name.startswith('us_side') and dist_cm < thresholds['slow']:
                slow_triggered = True

        if estop_triggered:
            if not self.estop_active:
                self.estop_active = True
                self.estop_start_time = now
                self.get_logger().warn('비상정지 발동!')
            self.cmd_vel_pub.publish(Twist())  # 즉시 정지
            self.speed_limit = 0.0

            # 비상정지 지속 시간 체크
            hold_sec = self.get_parameter('estop_hold_sec').value
            if (now - self.estop_start_time) > hold_sec:
                self.get_logger().warn(f'장애물 {hold_sec}초 지속 — 경로 재계획 요청')
                # TODO: Nav2 경로 재계획 서비스 호출
        elif slow_triggered:
            self.speed_limit = 0.5
            if self.estop_active:
                self.estop_active = False
                self.get_logger().info('장애물 제거 — 감속 모드')
        else:
            if self.estop_active or self.speed_limit < 1.0:
                self.estop_active = False
                self.speed_limit = 1.0
                self.get_logger().info('정상 주행 복귀')

        # 비상정지 이벤트 퍼블리시
        estop_msg = Bool()
        estop_msg.data = self.estop_active
        self.estop_pub.publish(estop_msg)

        # === 2. 배터리 체크 ===
        bat_low = self.get_parameter('battery_low_pct').value
        bat_critical = self.get_parameter('battery_critical_pct').value

        if self.battery_pct < bat_critical:
            self.get_logger().error(
                f'배터리 위험! {self.battery_pct:.0f}% — 즉시 정지'
            )
            self.emergency_stop('battery_critical')
        elif self.battery_pct < bat_low:
            self.get_logger().warn(
                f'배터리 부족 {self.battery_pct:.0f}% — 미션 중단, 집하장 복귀'
            )
            cmd = String()
            cmd.data = json.dumps({'action': 'abort', 'reason': 'battery_low'})
            self.mission_cmd_pub.publish(cmd)

        # === 3. 통신 체크 ===
        comm_timeout = self.get_parameter('comm_timeout_sec').value
        offline_timeout = self.get_parameter('comm_offline_timeout_sec').value

        if not self.mqtt_connected and self.mqtt_last_seen > 0:
            offline_duration = now - self.mqtt_last_seen
            if offline_duration > offline_timeout:
                self.get_logger().warn('통신 30초 끊김 — 집하장 자동 복귀')
                cmd = String()
                cmd.data = json.dumps({'action': 'abort', 'reason': 'comm_lost'})
                self.mission_cmd_pub.publish(cmd)
            elif offline_duration > comm_timeout:
                self.get_logger().info('통신 끊김 — 현재 위치 정지, 재연결 대기')
                self.cmd_vel_pub.publish(Twist())

    def emergency_stop(self, reason: str):
        """비상정지 — 모든 모터 즉시 정지"""
        self.cmd_vel_pub.publish(Twist())
        self.estop_active = True
        self.speed_limit = 0.0

        status = String()
        status.data = json.dumps({'estop': True, 'reason': reason})
        self.status_pub.publish(status)
        self.get_logger().error(f'비상정지: {reason}')

    def report_status(self):
        """1초마다 안전 상태 보고"""
        status = {
            'estop': self.estop_active,
            'speed_limit': self.speed_limit,
            'battery_pct': round(self.battery_pct, 1),
            'battery_v': round(self.battery_voltage, 2),
            'mqtt_connected': self.mqtt_connected,
            'nav_fail_count': self.nav_fail_count,
            'mode': self.current_mode,
            'ultrasonic': self.us_distances,
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SafetyManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
