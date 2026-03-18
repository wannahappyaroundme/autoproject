"""
네비게이션 노드 — Nav2를 통해 목표 좌표까지 자율 주행한다.

LiDAR 없는 구성:
  - SLAM: RTAB-Map Visual SLAM (RealSense D435 RGB-D)
  - 위치 추정: EKF (인코더 + IMU + Visual Odometry)
  - 장애물 감지: RealSense Depth → PointCloud → Costmap voxel_layer
  - 로컬 장애물: 초음파 5개 → Costmap range_sensor_layer

Nav2 Costmap 설정 (LiDAR 없이):
  global_costmap:
    plugins:
      - static_layer (RTAB-Map 맵 기반)
      - obstacle_layer (Depth 포인트클라우드)
      - inflation_layer

  local_costmap:
    plugins:
      - voxel_layer (RealSense Depth → 3D 장애물)
      - range_sensor_layer (초음파 5개 → 근접 장애물)
      - inflation_layer

토픽/액션:
  - /mission/goal (sub)           : mission_manager가 보내는 목표 좌표
  - /navigation/result (pub)      : 'arrived' | 'failed'
  - /robot/pose (sub)             : EKF 융합 위치 (ekf_localization에서)
  - /safety/estop (sub)           : 비상정지 시 목표 취소
  - NavigateToPose (action)       : Nav2 액션 클라이언트

Nav2 파라미터 참고 (depth 기반):
  voxel_layer:
    observation_sources: realsense_depth
    realsense_depth:
      topic: /camera/realsense/depth/points
      sensor_model: point_cloud
      min_obstacle_height: 0.05
      max_obstacle_height: 1.0
      clearing: true
      marking: true

  range_sensor_layer:
    observation_sources: us_front_left us_front_right us_side_left us_side_right us_rear
    us_front_left:
      topic: /ultrasonic/front_left
      sensor_model: range
      clear_threshold: 0.2

실행: ros2 run waste_robot navigation_node
"""

import math
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String, Bool
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose


class NavigationNode(Node):
    def __init__(self):
        super().__init__('navigation_node')

        # --- 파라미터 ---
        self.declare_parameter('approach_distance_m', 3.0)  # 모드 전환 트리거 거리
        self.declare_parameter('goal_tolerance_m', 0.3)      # 도착 판정 거리

        # --- Nav2 액션 클라이언트 ---
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # --- Publishers ---
        self.result_pub = self.create_publisher(String, '/navigation/result', 10)
        self.progress_pub = self.create_publisher(String, '/navigation/progress', 10)
        self.mode_switch_pub = self.create_publisher(String, '/mode/switch', 10)

        # --- Subscribers ---
        self.goal_sub = self.create_subscription(
            PoseStamped, '/mission/goal', self.on_goal, 10
        )
        self.pose_sub = self.create_subscription(
            PoseStamped, '/robot/pose', self.on_pose, 10
        )
        self.estop_sub = self.create_subscription(
            Bool, '/safety/estop', self.on_estop, 10
        )

        # --- 상태 ---
        self.current_pose = None
        self.current_goal = None
        self.active_goal_handle = None
        self.estop = False

        self.get_logger().info('NavigationNode 시작됨 (LiDAR-free: Depth + 초음파 기반)')

    def on_goal(self, msg: PoseStamped):
        """미션 매니저로부터 목표 좌표 수신 → Nav2에 전달"""
        self.current_goal = msg
        gx = msg.pose.position.x
        gy = msg.pose.position.y
        self.get_logger().info(f'목표 수신: ({gx:.1f}, {gy:.1f})')

        if self.estop:
            self.get_logger().warn('비상정지 중 — 목표 대기')
            return

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

        self.active_goal_handle = goal_handle
        self.get_logger().info('Nav2 목표 수락됨 — 주행 시작')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.on_nav_complete)

    def on_feedback(self, feedback_msg):
        """Nav2 피드백 — 남은 거리 확인 + 모드 전환 트리거"""
        fb = feedback_msg.feedback
        remaining = fb.distance_remaining if hasattr(fb, 'distance_remaining') else None

        if remaining is not None:
            # 진행 상태 퍼블리시
            progress = String()
            progress.data = f'{{"remaining_m": {remaining:.2f}}}'
            self.progress_pub.publish(progress)

            # 모드 전환 트리거: 목표까지 3m 이내이면 B→A 전환 요청
            approach_dist = self.get_parameter('approach_distance_m').value
            if remaining < approach_dist:
                switch_msg = String()
                switch_msg.data = 'A'
                self.mode_switch_pub.publish(switch_msg)

    def on_nav_complete(self, future):
        """Nav2 주행 완료"""
        self.active_goal_handle = None
        result = future.result()
        if result.status == 4:  # SUCCEEDED
            self.get_logger().info('목표 도착 완료')
            self.publish_result('arrived')
        else:
            self.get_logger().warn(f'주행 실패: status={result.status}')
            self.publish_result('failed')

    def on_pose(self, msg: PoseStamped):
        """EKF 융합 위치 수신"""
        self.current_pose = msg

    def on_estop(self, msg: Bool):
        """비상정지 이벤트"""
        self.estop = msg.data
        if self.estop and self.active_goal_handle:
            self.get_logger().warn('비상정지 — Nav2 목표 취소')
            self.active_goal_handle.cancel_goal_async()

    def publish_result(self, result: str):
        msg = String()
        msg.data = result
        self.result_pub.publish(msg)

    def distance_to_goal(self) -> float:
        """현재 위치에서 목표까지 거리"""
        if not self.current_pose or not self.current_goal:
            return float('inf')
        dx = self.current_goal.pose.position.x - self.current_pose.pose.position.x
        dy = self.current_goal.pose.position.y - self.current_pose.pose.position.y
        return math.sqrt(dx * dx + dy * dy)


def main(args=None):
    rclpy.init(args=args)
    node = NavigationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
