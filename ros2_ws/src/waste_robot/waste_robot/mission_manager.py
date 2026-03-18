"""
미션 관리 노드 — 수거 미션의 전체 흐름을 제어한다.

역할:
  1. 웹 서버(MQTT)로부터 미션 명령 수신
  2. 쓰레기통 목록을 받아 최적 수거 순서 계산 (nearest-neighbor)
  3. navigation_node에 목표 좌표 전달
  4. 수거 완료 시 다음 목표로 전환, 모두 완료 시 집하장(CP) 복귀

토픽/서비스:
  - /mission/command (sub)  : 미션 시작/중지/취소 명령
  - /mission/status (pub)   : 미션 진행 상태 (수거 중, 복귀 중, 완료 등)
  - /mission/goal (pub)     : 현재 목표 좌표 → navigation_node가 구독
  - /robot/state (pub)      : 로봇 상태 (idle, moving, collecting, returning)

실행: ros2 run waste_robot mission_manager
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped


class MissionManager(Node):
    def __init__(self):
        super().__init__('mission_manager')

        # --- Publishers ---
        self.status_pub = self.create_publisher(String, '/mission/status', 10)
        self.goal_pub = self.create_publisher(PoseStamped, '/mission/goal', 10)
        self.state_pub = self.create_publisher(String, '/robot/state', 10)

        # --- Subscribers ---
        self.command_sub = self.create_subscription(
            String, '/mission/command', self.on_command, 10
        )
        self.nav_result_sub = self.create_subscription(
            String, '/navigation/result', self.on_nav_result, 10
        )

        # --- 미션 상태 ---
        self.state = 'idle'          # idle | moving_to_bin | collecting | returning_to_cp
        self.bins = []               # [{ 'id': int, 'x': float, 'y': float }]
        self.current_idx = 0
        self.cp = {'x': 15.0, 'y': 20.0}  # 집하장 좌표 (맵 중앙)

        # 1초마다 상태 퍼블리시
        self.timer = self.create_timer(1.0, self.publish_state)

        self.get_logger().info('MissionManager 시작됨 — 미션 명령 대기 중')

    def on_command(self, msg: String):
        """미션 명령 수신 (JSON 형태: {"action": "start", "bins": [...]})"""
        import json
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'잘못된 명령: {msg.data}')
            return

        action = data.get('action')
        if action == 'start':
            self.bins = data.get('bins', [])
            self.current_idx = 0
            self.sort_bins_nearest()
            self.get_logger().info(f'미션 시작: 쓰레기통 {len(self.bins)}개')
            self.go_to_next_bin()
        elif action == 'stop':
            self.state = 'idle'
            self.get_logger().info('미션 중지')
        elif action == 'cancel':
            self.state = 'idle'
            self.bins = []
            self.get_logger().info('미션 취소')

    def sort_bins_nearest(self):
        """집하장에서 가장 가까운 순서로 정렬 (nearest-neighbor)"""
        sorted_bins = []
        remaining = list(self.bins)
        cx, cy = self.cp['x'], self.cp['y']
        while remaining:
            nearest = min(remaining, key=lambda b: abs(b['x'] - cx) + abs(b['y'] - cy))
            sorted_bins.append(nearest)
            cx, cy = nearest['x'], nearest['y']
            remaining.remove(nearest)
        self.bins = sorted_bins

    def go_to_next_bin(self):
        """다음 쓰레기통으로 이동 목표 전송"""
        if self.current_idx >= len(self.bins):
            # 모든 수거 완료 → 집하장 복귀
            self.state = 'returning_to_cp'
            self.publish_goal(self.cp['x'], self.cp['y'])
            return
        bin_info = self.bins[self.current_idx]
        self.state = 'moving_to_bin'
        self.publish_goal(bin_info['x'], bin_info['y'])
        self.get_logger().info(
            f'[{self.current_idx + 1}/{len(self.bins)}] 쓰레기통 #{bin_info["id"]}로 이동'
        )

    def on_nav_result(self, msg: String):
        """네비게이션 결과 수신 (arrived / failed)"""
        if msg.data == 'arrived':
            if self.state == 'moving_to_bin':
                # 쓰레기통 도착 → 수거 → 집하장 복귀
                self.state = 'collecting'
                self.get_logger().info('수거 중...')
                # TODO: 롤러 파지 명령 → serial_bridge로 전송
                # 수거 완료 가정 → 집하장 복귀
                self.state = 'returning_to_cp'
                self.publish_goal(self.cp['x'], self.cp['y'])
            elif self.state == 'returning_to_cp':
                # 집하장 도착 → 다음 쓰레기통으로
                self.get_logger().info('집하장 도착 — 하역 완료')
                self.current_idx += 1
                self.go_to_next_bin()

    def publish_goal(self, x: float, y: float):
        """PoseStamped 목표 퍼블리시"""
        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = x
        goal.pose.position.y = y
        self.goal_pub.publish(goal)

    def publish_state(self):
        """현재 상태 퍼블리시"""
        msg = String()
        msg.data = self.state
        self.state_pub.publish(msg)
        status = String()
        status.data = f'{self.state}|{self.current_idx}/{len(self.bins)}'
        self.status_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = MissionManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
