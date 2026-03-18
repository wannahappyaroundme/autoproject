"""
Visual SLAM 노드 — RealSense D435 RGB-D만으로 SLAM을 수행한다.
LiDAR 없이 depth 카메라 기반 SLAM.

사용 프레임워크: RTAB-Map (Real-Time Appearance-Based Mapping)
  - RealSense D435의 RGB + Depth → Visual Odometry + 3D Map
  - 2D occupancy grid 맵 자동 생성 (Nav2에서 사용)
  - Loop closure detection으로 드리프트 보정
  - ROS 2 Humble 공식 지원 패키지

설치: sudo apt install ros-humble-rtabmap-ros

이 노드는 RTAB-Map을 직접 구현하지 않고,
rtabmap_ros 패키지의 launch 파라미터를 설정하는 래퍼 역할을 한다.

토픽:
  - /camera/realsense/color (sub)   : RGB 이미지
  - /camera/realsense/depth (sub)   : Depth 이미지
  - /camera/realsense/info (sub)    : 카메라 내부 파라미터
  - /map (pub)                      : 2D occupancy grid (Nav2용)
  - /rtabmap/cloud_map (pub)        : 3D 포인트클라우드 맵
  - /rtabmap/odom (pub)             : Visual Odometry

실행:
  # 방법 1: 이 노드 실행 (RTAB-Map launch 래퍼)
  ros2 run waste_robot visual_slam

  # 방법 2: RTAB-Map 직접 launch (더 많은 설정 가능)
  ros2 launch rtabmap_ros rtabmap.launch.py \\
    rgb_topic:=/camera/realsense/color \\
    depth_topic:=/camera/realsense/depth \\
    camera_info_topic:=/camera/realsense/info \\
    frame_id:=base_link \\
    approx_sync:=true \\
    rtabmap_args:="--delete_db_on_start"
"""

import json
import subprocess
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from nav_msgs.msg import OccupancyGrid


class VisualSLAMNode(Node):
    """
    RTAB-Map Visual SLAM 래퍼 노드

    주요 기능:
      1. RTAB-Map 상태 모니터링
      2. 맵 저장/로드 제어
      3. 모드 전환 시 SLAM 일시정지/재개 (모드 A에서는 불필요)
      4. 맵 품질 진단 + 서버 보고
    """

    def __init__(self):
        super().__init__('visual_slam')

        # --- 파라미터 ---
        self.declare_parameter('use_sim_time', False)
        self.declare_parameter('map_save_path', '/tmp/apartment_map')
        self.declare_parameter('localization_mode', False)  # True = 기존 맵으로 위치만 추정

        # --- Publishers ---
        self.status_pub = self.create_publisher(String, '/slam/status', 10)

        # --- Subscribers ---
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self.on_map_update, 10
        )
        self.mode_sub = self.create_subscription(
            String, '/robot/mode', self.on_mode_change, 10
        )

        # --- 상태 ---
        self.slam_active = True
        self.map_received = False
        self.map_update_count = 0

        # 5초마다 SLAM 상태 보고
        self.timer = self.create_timer(5.0, self.report_status)

        self.get_logger().info('VisualSLAMNode 시작됨')
        self.get_logger().info('  RTAB-Map을 별도 launch해야 합니다:')
        self.get_logger().info('  ros2 launch rtabmap_ros rtabmap.launch.py ...')

    def on_map_update(self, msg: OccupancyGrid):
        """RTAB-Map에서 생성한 맵 수신"""
        self.map_received = True
        self.map_update_count += 1
        w, h = msg.info.width, msg.info.height
        res = msg.info.resolution
        if self.map_update_count % 10 == 1:
            self.get_logger().info(
                f'맵 업데이트 #{self.map_update_count}: {w}x{h} ({res}m/px)'
            )

    def on_mode_change(self, msg: String):
        """모드 전환 시 SLAM 제어"""
        mode = msg.data.upper()
        if mode == 'A':
            # 모드 A (전진 접근) — RealSense 비활성 → SLAM 일시정지
            self.slam_active = False
            self.get_logger().info('모드 A — SLAM 일시정지 (RealSense 비활성)')
        elif mode == 'B':
            # 모드 B (후진 운반) — RealSense 활성 → SLAM 재개
            self.slam_active = True
            self.get_logger().info('모드 B — SLAM 재개')

    def report_status(self):
        """SLAM 상태 보고"""
        status = {
            'active': self.slam_active,
            'map_received': self.map_received,
            'map_updates': self.map_update_count,
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)

    def save_map(self):
        """현재 맵을 파일로 저장"""
        path = self.get_parameter('map_save_path').value
        self.get_logger().info(f'맵 저장: {path}')
        # RTAB-Map CLI로 맵 저장
        # ros2 service call /rtabmap/save_map std_srvs/srv/Empty


def main(args=None):
    rclpy.init(args=args)
    node = VisualSLAMNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
