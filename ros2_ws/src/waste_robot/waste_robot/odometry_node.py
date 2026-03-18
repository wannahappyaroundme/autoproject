"""
오도메트리 노드 — 인코더 틱을 Odometry 메시지로 변환한다.

하드웨어 명세서 기준:
  - 바퀴 둘레: π × 80mm = 251.3mm
  - 인코더: 11 PPR × 30 (감속비) = 330 펄스/회전
  - 1펄스 = 251.3mm / 330 = 0.76mm 분해능
  - 좌우 바퀴 간격: 320mm

입력:
  - /encoder/ticks (sub)  : "DATA,ENC,<left>,<right>" (serial_bridge에서)

출력:
  - /odom (pub)           : nav_msgs/Odometry (EKF 입력)
  - /tf: odom → base_footprint

실행: ros2 run waste_robot odometry_node
"""

import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped, Quaternion
from tf2_ros import TransformBroadcaster


class OdometryNode(Node):
    def __init__(self):
        super().__init__('odometry_node')

        # --- 로봇 파라미터 (하드웨어 명세서 기준) ---
        self.declare_parameter('wheel_radius', 0.04)         # 80mm / 2
        self.declare_parameter('wheel_separation', 0.32)      # 320mm
        self.declare_parameter('ticks_per_rev', 330)           # 11 PPR × 30 감속비
        self.declare_parameter('publish_tf', True)

        self.wheel_radius = self.get_parameter('wheel_radius').value
        self.wheel_sep = self.get_parameter('wheel_separation').value
        self.ticks_per_rev = self.get_parameter('ticks_per_rev').value
        self.publish_tf = self.get_parameter('publish_tf').value

        # 1틱당 이동 거리 (m)
        wheel_circumference = 2.0 * math.pi * self.wheel_radius
        self.meters_per_tick = wheel_circumference / self.ticks_per_rev

        # --- 상태 ---
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.prev_left_ticks = None
        self.prev_right_ticks = None
        self.prev_time = None

        # --- Publishers ---
        self.odom_pub = self.create_publisher(Odometry, '/odom', 50)
        self.tf_broadcaster = TransformBroadcaster(self)

        # --- Subscribers ---
        self.enc_sub = self.create_subscription(
            String, '/encoder/ticks', self.on_encoder, 50
        )

        self.get_logger().info('OdometryNode 시작됨')
        self.get_logger().info(
            f'  바퀴 반지름: {self.wheel_radius*1000:.0f}mm, '
            f'간격: {self.wheel_sep*1000:.0f}mm, '
            f'분해능: {self.meters_per_tick*1000:.2f}mm/tick'
        )

    def on_encoder(self, msg: String):
        """인코더 데이터 수신 → 오도메트리 계산"""
        # 파싱: "DATA,ENC,<left>,<right>" 또는 JSON
        parts = msg.data.split(',')
        if len(parts) >= 4 and parts[0] == 'DATA' and parts[1] == 'ENC':
            left_ticks = int(parts[2])
            right_ticks = int(parts[3])
        else:
            return

        now = self.get_clock().now()

        if self.prev_left_ticks is None:
            self.prev_left_ticks = left_ticks
            self.prev_right_ticks = right_ticks
            self.prev_time = now
            return

        # 틱 변화량
        dl = (left_ticks - self.prev_left_ticks) * self.meters_per_tick
        dr = (right_ticks - self.prev_right_ticks) * self.meters_per_tick

        # 시간 변화
        dt = (now - self.prev_time).nanoseconds * 1e-9
        if dt <= 0:
            return

        self.prev_left_ticks = left_ticks
        self.prev_right_ticks = right_ticks
        self.prev_time = now

        # 디퍼렌셜 드라이브 오도메트리
        d_center = (dl + dr) / 2.0
        d_theta = (dr - dl) / self.wheel_sep

        # 위치 적분 (중점 룰)
        if abs(d_theta) < 1e-6:
            # 직선 이동
            self.x += d_center * math.cos(self.theta)
            self.y += d_center * math.sin(self.theta)
        else:
            # 원호 이동
            radius = d_center / d_theta
            self.x += radius * (math.sin(self.theta + d_theta) - math.sin(self.theta))
            self.y -= radius * (math.cos(self.theta + d_theta) - math.cos(self.theta))
        self.theta += d_theta
        # -π ~ π 정규화
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))

        # 속도 계산
        vx = d_center / dt
        vth = d_theta / dt

        # Odometry 메시지
        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_footprint'

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation = self._yaw_to_quaternion(self.theta)

        # 공분산 (인코더 기반 — 적당한 불확실성)
        odom.pose.covariance[0] = 0.01   # x
        odom.pose.covariance[7] = 0.01   # y
        odom.pose.covariance[35] = 0.03  # yaw

        odom.twist.twist.linear.x = vx
        odom.twist.twist.angular.z = vth
        odom.twist.covariance[0] = 0.01
        odom.twist.covariance[35] = 0.03

        self.odom_pub.publish(odom)

        # TF 브로드캐스트: odom → base_footprint
        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = now.to_msg()
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_footprint'
            t.transform.translation.x = self.x
            t.transform.translation.y = self.y
            q = self._yaw_to_quaternion(self.theta)
            t.transform.rotation = q
            self.tf_broadcaster.sendTransform(t)

    @staticmethod
    def _yaw_to_quaternion(yaw: float) -> Quaternion:
        q = Quaternion()
        q.w = math.cos(yaw / 2.0)
        q.z = math.sin(yaw / 2.0)
        return q


def main(args=None):
    rclpy.init(args=args)
    node = OdometryNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
