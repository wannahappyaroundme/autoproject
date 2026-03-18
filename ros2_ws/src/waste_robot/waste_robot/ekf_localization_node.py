"""
EKF 센서 퓨전 노드 — 여러 센서의 위치 추정값을 융합하여 정확한 위치를 산출한다.

사용 프레임워크: robot_localization (ROS 2 공식 패키지)
  - Extended Kalman Filter (EKF)
  - 인코더 오도메트리 + IMU + Visual Odometry (RTAB-Map) 융합

설치: sudo apt install ros-humble-robot-localization

융합 센서:
  1. 인코더 오도메트리 (/odom)       — 상대 이동 거리 (드리프트 있음)
  2. IMU (/imu/data)                  — 가속도/각속도 (회전 정확, 이동 부정확)
  3. Visual Odometry (/rtabmap/odom)  — RTAB-Map 시각 주행거리 (절대 위치 보정)

출력:
  - /odometry/filtered               — EKF 융합 결과 (최종 위치)
  - /tf: odom → base_link            — TF 트리 업데이트

이 노드는 robot_localization의 ekf_node를 직접 구현하지 않고,
YAML 파라미터 설정을 관리하고 상태를 모니터링하는 래퍼 역할을 한다.

실행:
  # 방법 1: robot_localization 직접 실행
  ros2 launch robot_localization ekf.launch.py

  # 방법 2: 파라미터 파일 지정
  ros2 run robot_localization ekf_node \\
    --ros-args --params-file config/ekf_params.yaml

EKF 파라미터 (config/ekf_params.yaml):
  ekf_filter_node:
    ros__parameters:
      frequency: 50.0
      sensor_timeout: 0.1
      two_d_mode: true          # 평면 주행 → 2D 모드
      publish_tf: true
      map_frame: map
      odom_frame: odom
      base_link_frame: base_link
      world_frame: odom

      # 센서 0: 인코더 오도메트리
      odom0: /odom
      odom0_config: [true,  true,  false,   # x, y, z
                     false, false, true,     # roll, pitch, yaw
                     false, false, false,    # vx, vy, vz
                     false, false, true,     # vroll, vpitch, vyaw
                     false, false, false]    # ax, ay, az

      # 센서 1: IMU
      imu0: /imu/data
      imu0_config: [false, false, false,    # x, y, z
                    true,  true,  true,     # roll, pitch, yaw
                    false, false, false,    # vx, vy, vz
                    true,  true,  true,     # vroll, vpitch, vyaw
                    true,  true,  true]     # ax, ay, az

      # 센서 2: Visual Odometry (RTAB-Map)
      odom1: /rtabmap/odom
      odom1_config: [true,  true,  false,   # x, y, z (절대 위치 보정)
                     false, false, true,     # yaw 보정
                     false, false, false,
                     false, false, false,
                     false, false, false]
"""

import json
import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from geometry_msgs.msg import PoseStamped, TransformStamped

# TODO: 실제 실행 시 활성화
# from tf2_ros import TransformBroadcaster


class EKFLocalizationNode(Node):
    """
    EKF 센서 퓨전 모니터링 노드

    robot_localization 패키지가 실제 EKF를 수행하고,
    이 노드는 상태 모니터링 + 진단 + 웹 서버 보고를 담당한다.
    """

    def __init__(self):
        super().__init__('ekf_localization')

        # --- Subscribers (센서 입력 모니터링) ---
        self.odom_sub = self.create_subscription(
            Odometry, '/odom', self.on_encoder_odom, 10
        )
        self.imu_sub = self.create_subscription(
            Imu, '/imu/data', self.on_imu, 10
        )
        self.visual_odom_sub = self.create_subscription(
            Odometry, '/rtabmap/odom', self.on_visual_odom, 10
        )
        self.filtered_sub = self.create_subscription(
            Odometry, '/odometry/filtered', self.on_filtered_odom, 10
        )

        # --- Publishers ---
        self.status_pub = self.create_publisher(String, '/localization/status', 10)
        self.pose_pub = self.create_publisher(PoseStamped, '/robot/pose', 10)

        # --- 센서 상태 추적 ---
        self.sensor_status = {
            'encoder': {'active': False, 'last_time': 0.0, 'hz': 0.0},
            'imu': {'active': False, 'last_time': 0.0, 'hz': 0.0},
            'visual_odom': {'active': False, 'last_time': 0.0, 'hz': 0.0},
            'ekf_output': {'active': False, 'last_time': 0.0, 'hz': 0.0},
        }

        # --- EKF 출력 ---
        self.filtered_pose = None
        self.msg_counts = {'encoder': 0, 'imu': 0, 'visual_odom': 0, 'ekf': 0}

        # 2초마다 상태 보고
        self.timer = self.create_timer(2.0, self.report_status)
        # 10초마다 센서 건강 체크
        self.health_timer = self.create_timer(10.0, self.check_sensor_health)

        self.get_logger().info('EKFLocalizationNode 시작됨')
        self.get_logger().info('  robot_localization ekf_node를 별도 실행해야 합니다')

    def _update_sensor(self, name: str):
        now = self.get_clock().now().nanoseconds * 1e-9
        s = self.sensor_status[name]
        if s['last_time'] > 0:
            dt = now - s['last_time']
            if dt > 0:
                s['hz'] = 0.9 * s['hz'] + 0.1 * (1.0 / dt)  # EMA 필터
        s['last_time'] = now
        s['active'] = True
        self.msg_counts[name] = self.msg_counts.get(name, 0) + 1

    def on_encoder_odom(self, msg: Odometry):
        self._update_sensor('encoder')

    def on_imu(self, msg: Imu):
        self._update_sensor('imu')

    def on_visual_odom(self, msg: Odometry):
        self._update_sensor('visual_odom')

    def on_filtered_odom(self, msg: Odometry):
        """EKF 융합 결과 수신 → /robot/pose로 재퍼블리시"""
        self._update_sensor('ekf')
        self.filtered_pose = msg

        # /robot/pose 퍼블리시 (웹 서버로 전달됨)
        pose = PoseStamped()
        pose.header = msg.header
        pose.pose = msg.pose.pose
        self.pose_pub.publish(pose)

    def report_status(self):
        """센서 퓨전 상태 보고"""
        status = {}
        for name, s in self.sensor_status.items():
            status[name] = {
                'active': s['active'],
                'hz': round(s['hz'], 1),
            }

        if self.filtered_pose:
            p = self.filtered_pose.pose.pose.position
            q = self.filtered_pose.pose.pose.orientation
            # quaternion → yaw
            yaw = math.atan2(
                2.0 * (q.w * q.z + q.x * q.y),
                1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            )
            status['pose'] = {
                'x': round(p.x, 3),
                'y': round(p.y, 3),
                'yaw_deg': round(math.degrees(yaw), 1),
            }

        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)

    def check_sensor_health(self):
        """센서 데이터가 끊기면 경고"""
        now = self.get_clock().now().nanoseconds * 1e-9
        for name, s in self.sensor_status.items():
            if s['active'] and s['last_time'] > 0:
                age = now - s['last_time']
                if age > 2.0:
                    s['active'] = False
                    self.get_logger().warn(
                        f'센서 {name} 데이터 끊김 ({age:.1f}초 전 마지막 수신)'
                    )


def main(args=None):
    rclpy.init(args=args)
    node = EKFLocalizationNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
