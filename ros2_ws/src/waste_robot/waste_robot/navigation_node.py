"""
네비게이션 노드 — Nav2를 통해 목표 좌표까지 자율 주행한다.

역할:
  1. /mission/goal 토픽에서 목표 좌표 수신
  2. Nav2 NavigateToPose 액션 서버에 목표 전달
  3. 도착 또는 실패 시 /navigation/result로 결과 퍼블리시
  4. 주행 중 현재 위치를 /robot/pose로 퍼블리시 (웹 서버 전달용)

토픽/액션:
  - /mission/goal (sub)        : mission_manager가 보내는 목표 좌표
  - /navigation/result (pub)   : 'arrived' | 'failed'
  - /robot/pose (pub)          : 현재 로봇 위치 (x, y, heading)
  - NavigateToPose (action)    : Nav2 액션 클라이언트

실행: ros2 run waste_robot navigation_node
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose


class NavigationNode(Node):
    def __init__(self):
        super().__init__('navigation_node')

        # --- Nav2 액션 클라이언트 ---
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # --- Publishers ---
        self.result_pub = self.create_publisher(String, '/navigation/result', 10)
        self.pose_pub = self.create_publisher(PoseStamped, '/robot/pose', 10)

        # --- Subscribers ---
        self.goal_sub = self.create_subscription(
            PoseStamped, '/mission/goal', self.on_goal, 10
        )
        # AMCL 위치 추정값 구독
        self.amcl_sub = self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl_pose, 10
        )

        self.current_pose = None
        self.get_logger().info('NavigationNode 시작됨 — Nav2 액션 서버 대기')

    def on_goal(self, msg: PoseStamped):
        """미션 매니저로부터 목표 좌표 수신 → Nav2에 전달"""
        self.get_logger().info(
            f'목표 수신: ({msg.pose.position.x:.1f}, {msg.pose.position.y:.1f})'
        )

        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Nav2 액션 서버 연결 실패')
            self.publish_result('failed')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = msg

        send_goal_future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self.on_feedback
        )
        send_goal_future.add_done_callback(self.on_goal_response)

    def on_goal_response(self, future):
        """Nav2 목표 수락 여부"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Nav2가 목표를 거절함')
            self.publish_result('failed')
            return

        self.get_logger().info('Nav2 목표 수락됨 — 주행 시작')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.on_nav_complete)

    def on_feedback(self, feedback_msg):
        """Nav2 피드백 (현재 위치, 남은 거리 등)"""
        # TODO: 남은 거리/시간 정보를 웹 서버에 전달
        pass

    def on_nav_complete(self, future):
        """Nav2 주행 완료"""
        result = future.result()
        if result.status == 4:  # SUCCEEDED
            self.get_logger().info('목표 도착 완료')
            self.publish_result('arrived')
        else:
            self.get_logger().warn(f'주행 실패: status={result.status}')
            self.publish_result('failed')

    def on_amcl_pose(self, msg: PoseWithCovarianceStamped):
        """AMCL 위치 추정값 → /robot/pose로 재퍼블리시"""
        pose = PoseStamped()
        pose.header = msg.header
        pose.pose = msg.pose.pose
        self.pose_pub.publish(pose)
        self.current_pose = pose

    def publish_result(self, result: str):
        msg = String()
        msg.data = result
        self.result_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = NavigationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
