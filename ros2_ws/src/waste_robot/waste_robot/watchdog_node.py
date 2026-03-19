"""
워치독 (헬스 모니터) 노드 — 전체 시스템의 건강 상태를 감시한다.

역할:
  1. 각 노드의 heartbeat 수신 → 생존 여부 판단
  2. 5초 무응답 → DEAD 마킹
  3. 10초 무응답 → subprocess로 재시작 시도
  4. 로봇 상태 고착 감지 (120초 이상 동일 상태)
  5. 에러 수집 및 에스컬레이션
  6. 시스템 건강 점수 계산 (0–100)

토픽:
  구독:
    /NODE_NAME/heartbeat  (std_msgs/String)  — 노드별 하트비트 (매 1초)
    /robot/state          (std_msgs/String)  — 로봇 상태 감시
    /robot/error          (std_msgs/String)  — 에러 수집
    /battery/level        (std_msgs/Float32) — 배터리 감시
  발행:
    /watchdog/status      (std_msgs/String)  — JSON: 전체 노드 상태
    /watchdog/alert       (std_msgs/String)  — 위험 알림

실행: ros2 run waste_robot watchdog_node
"""

import json
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32


class NodeStatus:
    """개별 노드 상태 추적"""
    ALIVE = 'ALIVE'
    WARN = 'WARN'
    DEAD = 'DEAD'
    RESTARTING = 'RESTARTING'

    def __init__(self, node_name: str, executable: str):
        self.node_name = node_name
        self.executable = executable  # ros2 run 실행명
        self.status = self.ALIVE
        self.last_heartbeat = time.time()
        self.restart_count = 0
        self.max_restarts = 3


class WatchdogNode(Node):
    def __init__(self):
        super().__init__('watchdog_node')

        # --- 파라미터 ---
        self.declare_parameter('heartbeat_warn_sec', 5.0)
        self.declare_parameter('heartbeat_dead_sec', 10.0)
        self.declare_parameter('stuck_state_sec', 120.0)
        self.declare_parameter('battery_critical_threshold', 10.0)
        self.declare_parameter('max_restart_attempts', 3)

        # --- 감시 대상 노드 목록 ---
        # (노드 이름, ros2 run 실행 가능한 이름)
        monitored_nodes = [
            ('mission_manager', 'mission_manager'),
            ('robot_fsm', 'fsm_node'),
            ('navigation_node', 'navigation_node'),
            ('qr_detector', 'qr_detector'),
            ('serial_bridge', 'serial_bridge'),
            ('battery_manager', 'battery_manager_node'),
            ('multi_robot_coordinator', 'multi_robot_coordinator'),
        ]
        self.nodes = {
            name: NodeStatus(name, exe)
            for name, exe in monitored_nodes
        }

        # --- 로봇 상태 감시 ---
        self.robot_state = 'IDLE'
        self.robot_state_since = time.time()
        self.battery_level = 100.0
        self.error_log: list = []

        # --- Publishers ---
        self.status_pub = self.create_publisher(
            String, '/watchdog/status', 10
        )
        self.alert_pub = self.create_publisher(
            String, '/watchdog/alert', 10
        )

        # --- Subscribers ---
        # 각 노드의 하트비트 구독
        for node_name in self.nodes:
            self.create_subscription(
                String, f'/{node_name}/heartbeat',
                lambda msg, n=node_name: self.on_heartbeat(n, msg), 10
            )

        self.create_subscription(
            String, '/robot/state', self.on_robot_state, 10
        )
        self.create_subscription(
            String, '/robot/error', self.on_robot_error, 10
        )
        self.create_subscription(
            Float32, '/battery/level', self.on_battery_level, 10
        )

        # --- 타이머 ---
        self.create_timer(2.0, self.check_heartbeats)
        self.create_timer(5.0, self.check_stuck_state)
        self.create_timer(3.0, self.publish_status)

        self.get_logger().info(
            f'WatchdogNode 시작됨 — {len(self.nodes)}개 노드 감시 중'
        )

    # ──────────────────────────────────────────────
    # 하트비트 수신
    # ──────────────────────────────────────────────
    def on_heartbeat(self, node_name: str, msg: String):
        if node_name in self.nodes:
            ns = self.nodes[node_name]
            ns.last_heartbeat = time.time()
            if ns.status in (NodeStatus.DEAD, NodeStatus.WARN,
                             NodeStatus.RESTARTING):
                old = ns.status
                ns.status = NodeStatus.ALIVE
                self.get_logger().info(
                    f'[워치독] {node_name}: {old} → ALIVE (복구됨)'
                )

    # ──────────────────────────────────────────────
    # 하트비트 검사
    # ──────────────────────────────────────────────
    def check_heartbeats(self):
        now = time.time()
        warn_sec = self.get_parameter(
            'heartbeat_warn_sec'
        ).get_parameter_value().double_value
        dead_sec = self.get_parameter(
            'heartbeat_dead_sec'
        ).get_parameter_value().double_value
        max_restarts = self.get_parameter(
            'max_restart_attempts'
        ).get_parameter_value().integer_value

        for name, ns in self.nodes.items():
            elapsed = now - ns.last_heartbeat

            if elapsed >= dead_sec:
                if ns.status != NodeStatus.DEAD:
                    ns.status = NodeStatus.DEAD
                    self.get_logger().error(
                        f'[워치독] {name}: DEAD '
                        f'(하트비트 {elapsed:.1f}s 전)'
                    )
                    self.publish_alert(
                        f'노드 {name} 응답 없음 ({elapsed:.0f}s)'
                    )
                # 재시작 시도
                if ns.restart_count < max_restarts:
                    self._attempt_restart(ns)

            elif elapsed >= warn_sec:
                if ns.status == NodeStatus.ALIVE:
                    ns.status = NodeStatus.WARN
                    self.get_logger().warn(
                        f'[워치독] {name}: WARN '
                        f'(하트비트 {elapsed:.1f}s 전)'
                    )

    def _attempt_restart(self, ns: NodeStatus):
        """subprocess로 노드 재시작 시도"""
        ns.restart_count += 1
        ns.status = NodeStatus.RESTARTING
        self.get_logger().warn(
            f'[워치독] {ns.node_name} 재시작 시도 '
            f'({ns.restart_count}/{ns.max_restarts})'
        )
        try:
            subprocess.Popen(
                ['ros2', 'run', 'waste_robot', ns.executable],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.publish_alert(
                f'노드 {ns.node_name} 재시작 시도 '
                f'({ns.restart_count}/{ns.max_restarts})'
            )
        except Exception as e:
            self.get_logger().error(
                f'[워치독] {ns.node_name} 재시작 실패: {e}'
            )
            self.publish_alert(
                f'노드 {ns.node_name} 재시작 실패: {e}'
            )

    # ──────────────────────────────────────────────
    # 로봇 상태 고착 감지
    # ──────────────────────────────────────────────
    def on_robot_state(self, msg: String):
        new_state = msg.data
        if new_state != self.robot_state:
            self.robot_state = new_state
            self.robot_state_since = time.time()

    def check_stuck_state(self):
        stuck_sec = self.get_parameter(
            'stuck_state_sec'
        ).get_parameter_value().double_value
        elapsed = time.time() - self.robot_state_since

        # IDLE, CHARGING은 고착이 아님
        if self.robot_state in ('IDLE', 'CHARGING'):
            return

        if elapsed > stuck_sec:
            self.get_logger().warn(
                f'[워치독] 로봇 상태 고착: {self.robot_state} '
                f'({elapsed:.0f}s > {stuck_sec:.0f}s)'
            )
            self.publish_alert(
                f'로봇 상태 고착: {self.robot_state} ({elapsed:.0f}s)'
            )
            # 타이머 리셋 — 반복 알림 방지
            self.robot_state_since = time.time()

    # ──────────────────────────────────────────────
    # 에러 수집
    # ──────────────────────────────────────────────
    def on_robot_error(self, msg: String):
        error_entry = {
            'time': time.time(),
            'message': msg.data,
        }
        self.error_log.append(error_entry)
        # 최근 100개만 유지
        if len(self.error_log) > 100:
            self.error_log = self.error_log[-100:]
        self.get_logger().error(f'[워치독 에러 수집] {msg.data}')
        self.publish_alert(f'로봇 에러: {msg.data}')

    # ──────────────────────────────────────────────
    # 배터리 감시
    # ──────────────────────────────────────────────
    def on_battery_level(self, msg: Float32):
        self.battery_level = msg.data
        critical = self.get_parameter(
            'battery_critical_threshold'
        ).get_parameter_value().double_value
        if msg.data < critical:
            self.get_logger().error(
                f'[워치독] 배터리 위험: {msg.data:.1f}%'
            )
            self.publish_alert(f'배터리 위험: {msg.data:.1f}%')

    # ──────────────────────────────────────────────
    # 시스템 건강 점수
    # ──────────────────────────────────────────────
    def calculate_health_score(self) -> int:
        """시스템 건강 점수 0–100"""
        score = 100
        total_nodes = len(self.nodes)
        if total_nodes == 0:
            return score

        for ns in self.nodes.values():
            if ns.status == NodeStatus.DEAD:
                score -= 20
            elif ns.status == NodeStatus.WARN:
                score -= 5
            elif ns.status == NodeStatus.RESTARTING:
                score -= 10

        # 배터리 패널티
        if self.battery_level < 10:
            score -= 15
        elif self.battery_level < 20:
            score -= 5

        # 최근 에러 패널티 (최근 60초 에러 수)
        recent_errors = sum(
            1 for e in self.error_log
            if time.time() - e['time'] < 60
        )
        score -= min(recent_errors * 3, 20)

        # 상태 고착 패널티
        if self.robot_state not in ('IDLE', 'CHARGING'):
            stuck_sec = self.get_parameter(
                'stuck_state_sec'
            ).get_parameter_value().double_value
            elapsed = time.time() - self.robot_state_since
            if elapsed > stuck_sec * 0.5:
                score -= 10

        return max(0, min(100, score))

    # ──────────────────────────────────────────────
    # 상태/알림 퍼블리시
    # ──────────────────────────────────────────────
    def publish_status(self):
        status = {
            'health_score': self.calculate_health_score(),
            'robot_state': self.robot_state,
            'battery': self.battery_level,
            'nodes': {
                name: {
                    'status': ns.status,
                    'last_heartbeat_ago': round(
                        time.time() - ns.last_heartbeat, 1
                    ),
                    'restart_count': ns.restart_count,
                }
                for name, ns in self.nodes.items()
            },
            'recent_errors': len([
                e for e in self.error_log
                if time.time() - e['time'] < 60
            ]),
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)

    def publish_alert(self, message: str):
        msg = String()
        msg.data = json.dumps({
            'time': time.time(),
            'alert': message,
        })
        self.alert_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = WatchdogNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('WatchdogNode 종료')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
