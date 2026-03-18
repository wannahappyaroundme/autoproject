"""
Visual Servoing 노드 — 카메라 A(웹캠)로 쓰레기통에 정밀 접근한다.

역할:
  1. 카메라 A에서 QR 코드 또는 쓰레기통 탐지
  2. 이미지 상의 타겟 위치 → 오차 계산
  3. 오차를 줄이는 방향으로 /cmd_vel 퍼블리시 (저속 미세 조정)
  4. 오차가 허용 범위 이내이면 정지 + 파지 준비 완료 신호

알고리즘: IBVS (Image-Based Visual Servoing)
  - 타겟(QR/쓰레기통)의 이미지 좌표가 화면 중앙에 오도록 조향
  - PnP로 거리 추정 → 목표 거리(0.15m)에 도달하면 정지
  - PID 제어로 부드러운 접근

토픽:
  - /camera/webcam/color (sub)   : 카메라 A RGB 이미지
  - /qr/detected (sub)           : QR 인식 결과 (qr_detector_node에서)
  - /cmd_vel (pub)               : 저속 이동 명령
  - /servo/status (pub)          : 서보잉 상태 (aligning, aligned, lost)
  - /servo/ready (pub)           : 파지 준비 완료 신호

실행: ros2 run waste_robot visual_servo
"""

import json
import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image


class PIDController:
    """단순 PID 제어기"""

    def __init__(self, kp: float, ki: float, kd: float, limit: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.limit = limit
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error: float, dt: float) -> float:
        self.integral += error * dt
        # 적분 와인드업 방지
        self.integral = max(-self.limit * 2, min(self.limit * 2, self.integral))
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        self.prev_error = error

        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        return max(-self.limit, min(self.limit, output))

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0


class VisualServoNode(Node):
    """
    IBVS (Image-Based Visual Servoing) 컨트롤러

    화면 중앙에 쓰레기통을 정렬하고, 목표 거리까지 접근한다.
    """

    def __init__(self):
        super().__init__('visual_servo')

        # --- 파라미터 ---
        self.declare_parameter('target_distance_m', 0.15)    # 파지 최적 거리
        self.declare_parameter('distance_tolerance_m', 0.03)  # ±3cm
        self.declare_parameter('angle_tolerance_deg', 3.0)    # ±3도
        self.declare_parameter('max_linear_speed', 0.1)       # 최대 전진 속도
        self.declare_parameter('max_angular_speed', 0.3)      # 최대 회전 속도
        self.declare_parameter('image_width', 1920)
        self.declare_parameter('image_height', 1080)
        self.declare_parameter('timeout_sec', 30.0)           # 서보잉 타임아웃

        target_dist = self.get_parameter('target_distance_m').value
        self.img_w = self.get_parameter('image_width').value
        self.img_h = self.get_parameter('image_height').value
        max_lin = self.get_parameter('max_linear_speed').value
        max_ang = self.get_parameter('max_angular_speed').value

        # --- PID 컨트롤러 ---
        # 횡방향 (좌우 정렬) — 화면 중앙 기준 오차
        self.lateral_pid = PIDController(kp=0.8, ki=0.05, kd=0.1, limit=max_ang)
        # 종방향 (거리 접근)
        self.distance_pid = PIDController(kp=0.5, ki=0.02, kd=0.08, limit=max_lin)

        # --- Publishers ---
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.status_pub = self.create_publisher(String, '/servo/status', 10)
        self.ready_pub = self.create_publisher(Bool, '/servo/ready', 10)

        # --- Subscribers ---
        self.qr_sub = self.create_subscription(
            String, '/qr/detected', self.on_qr_detected, 10
        )
        self.qr_dist_sub = self.create_subscription(
            String, '/qr/distance', self.on_qr_distance, 10
        )

        # --- 상태 ---
        self.state = 'idle'       # idle | aligning | aligned | lost
        self.target_center_x = 0  # QR 중심 x좌표 (픽셀)
        self.target_distance = 0.0  # QR까지 거리 (m)
        self.target_angle = 0.0     # QR 각도 (deg)
        self.last_detection_time = 0.0
        self.servo_start_time = 0.0

        # 20Hz 제어 루프
        self.timer = self.create_timer(0.05, self.control_loop)

        self.get_logger().info('VisualServoNode 시작됨')
        self.get_logger().info(f'  목표 거리: {target_dist}m, 허용 오차: ±3cm, ±3°')

    def on_qr_detected(self, msg: String):
        """QR 인식 결과 수신 (qr_detector_node에서)"""
        try:
            data = json.loads(msg.data)
            # QR 코드 바운딩 박스 중심 좌표
            if 'center_x' in data:
                self.target_center_x = data['center_x']
                self.last_detection_time = self.get_clock().now().nanoseconds * 1e-9
                if self.state == 'idle' or self.state == 'lost':
                    self.state = 'aligning'
                    self.servo_start_time = self.last_detection_time
                    self.lateral_pid.reset()
                    self.distance_pid.reset()
                    self.get_logger().info('QR 탐지됨 — Visual Servoing 시작')
        except json.JSONDecodeError:
            pass

    def on_qr_distance(self, msg: String):
        """QR 거리/각도 정보 수신"""
        try:
            data = json.loads(msg.data)
            self.target_distance = data.get('distance_m', 0.0)
            self.target_angle = data.get('angle_deg', 0.0)
        except json.JSONDecodeError:
            pass

    def control_loop(self):
        """20Hz 제어 루프 — PID로 cmd_vel 계산"""
        if self.state == 'idle':
            return

        now = self.get_clock().now().nanoseconds * 1e-9
        dt = 0.05  # 20Hz

        # 타임아웃 체크
        timeout = self.get_parameter('timeout_sec').value
        if self.servo_start_time > 0 and (now - self.servo_start_time) > timeout:
            self.get_logger().warn('Visual Servoing 타임아웃 — 정지')
            self.stop_and_report('timeout')
            return

        # QR 탐지 끊김 체크 (1초 이상)
        if (now - self.last_detection_time) > 1.0:
            self.state = 'lost'
            self.publish_status('lost')
            # 정지
            self.cmd_vel_pub.publish(Twist())
            return

        # --- 횡방향 오차: 화면 중앙(img_w/2) 기준 ---
        center_error = (self.target_center_x - self.img_w / 2) / (self.img_w / 2)
        # -1.0 ~ +1.0 범위 (좌=-1, 우=+1)
        angular_z = -self.lateral_pid.compute(center_error, dt)

        # --- 종방향 오차: 목표 거리까지 ---
        target_dist = self.get_parameter('target_distance_m').value
        dist_tolerance = self.get_parameter('distance_tolerance_m').value
        angle_tolerance = self.get_parameter('angle_tolerance_deg').value

        dist_error = self.target_distance - target_dist
        linear_x = self.distance_pid.compute(dist_error, dt) if self.target_distance > 0 else 0.0

        # --- 정렬 완료 판정 ---
        angle_aligned = abs(center_error) < (angle_tolerance / 45.0)
        dist_aligned = abs(dist_error) < dist_tolerance if self.target_distance > 0 else False

        if angle_aligned and dist_aligned:
            self.stop_and_report('aligned')
            return

        # --- cmd_vel 퍼블리시 ---
        cmd = Twist()
        cmd.linear.x = max(0.0, linear_x)  # 전진만 (후진 금지)
        cmd.angular.z = angular_z
        self.cmd_vel_pub.publish(cmd)

        self.publish_status('aligning')

    def stop_and_report(self, result: str):
        """정지 + 결과 보고"""
        self.cmd_vel_pub.publish(Twist())  # 정지
        self.state = 'aligned' if result == 'aligned' else 'idle'

        self.publish_status(result)

        # 파지 준비 완료 신호
        ready_msg = Bool()
        ready_msg.data = (result == 'aligned')
        self.ready_pub.publish(ready_msg)

        if result == 'aligned':
            self.get_logger().info(
                f'정렬 완료! 거리: {self.target_distance:.3f}m, '
                f'중심 오차: {self.target_center_x - self.img_w/2:.0f}px'
            )
        else:
            self.get_logger().warn(f'Visual Servoing 종료: {result}')

    def publish_status(self, status: str):
        msg = String()
        msg.data = json.dumps({
            'state': status,
            'distance_m': round(self.target_distance, 3),
            'center_error_px': round(self.target_center_x - self.img_w / 2, 1),
        })
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = VisualServoNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
