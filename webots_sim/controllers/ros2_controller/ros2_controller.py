"""
Webots ROS 2 컨트롤러 — EXTERN 모드 지원

실행 구조:
  [Mac]  Webots GUI (apartment_complex.wbt, controller "<extern>")
            │
            │  TCP (포트 1234)
            │
  [UTM Ubuntu]  이 스크립트 (ros2_controller.py)
            │
            │  ROS 2 토픽
            │
  [UTM Ubuntu]  ROS 2 노드들 (navigation, fsm, mission_manager, ...)

퍼블리시 (Webots → ROS 2):
  /camera/front/image_raw      sensor_msgs/Image      전면 RGB (640x480, bgra8)
  /camera/rear/image_raw       sensor_msgs/Image      후면 RGB (640x480, bgra8)
  /camera/depth/image_raw      sensor_msgs/Image      깊이 (640x480, 32FC1)
  /ultrasonic/front_center     sensor_msgs/Range      전방 중앙 초음파 (0~2m)
  /ultrasonic/front_left       sensor_msgs/Range      전방 좌측
  /ultrasonic/front_right      sensor_msgs/Range      전방 우측
  /ultrasonic/left             sensor_msgs/Range      좌측
  /ultrasonic/right            sensor_msgs/Range      우측
  /imu/data                    sensor_msgs/Imu        방향+각속도+선가속도
  /wheel/left/position         std_msgs/Float64       좌측 엔코더 (rad)
  /wheel/right/position        std_msgs/Float64       우측 엔코더 (rad)

구독 (ROS 2 → Webots):
  /cmd_vel                     geometry_msgs/Twist    속도 → 디퍼렌셜 구동

실행 방법 (UTM Ubuntu에서):
  # 1. webots-controller 패키지 설치
  pip3 install webots-controller

  # 2. 환경변수 설정 (MAC_IP는 Mac의 IP)
  export WEBOTS_CONTROLLER_URL=tcp://MAC_IP:1234/waste_robot

  # 3. ROS 2 소싱 후 실행
  source /opt/ros/humble/setup.bash
  python3 ros2_controller.py

  또는 launch 파일 사용:
  ros2 launch webots_sim webots_launch.py webots_url:=tcp://MAC_IP:1234/waste_robot
"""

import argparse
import math
import os
import struct
import sys
import time

# ── EXTERN 모드: WEBOTS_CONTROLLER_URL 환경변수 설정 ──────────
# Webots가 Mac에서 돌고, 이 스크립트가 UTM Ubuntu에서 돌 때 필요
# 환경변수가 이미 설정되어 있으면 그대로 사용
# CLI 인자로도 받을 수 있음: python3 ros2_controller.py --url tcp://192.168.64.1:1234/waste_robot

def _setup_extern_url():
    """CLI 인자 또는 환경변수에서 Webots 연결 URL 결정"""
    parser = argparse.ArgumentParser(description='Webots ROS 2 Extern Controller')
    parser.add_argument(
        '--url',
        default=os.environ.get('WEBOTS_CONTROLLER_URL', ''),
        help='Webots extern controller URL (예: tcp://192.168.64.1:1234/waste_robot)',
    )
    args, _ = parser.parse_known_args()

    if args.url:
        os.environ['WEBOTS_CONTROLLER_URL'] = args.url
        print(f'[EXTERN] WEBOTS_CONTROLLER_URL = {args.url}')
    elif 'WEBOTS_CONTROLLER_URL' not in os.environ:
        print('[INFO] WEBOTS_CONTROLLER_URL 미설정 — Webots 내부 컨트롤러 모드로 실행')


# 환경변수를 먼저 설정해야 controller import 시 TCP 연결됨
_setup_extern_url()

# ── Webots Controller API ─────────────────────────────────────
try:
    from controller import Robot as WebotsRobot
    WEBOTS_AVAILABLE = True
except ImportError:
    WEBOTS_AVAILABLE = False
    print('[WARN] Webots controller 모듈 없음')
    print('  pip3 install webots-controller  (UTM Ubuntu용)')
    print('  또는 Webots 내부에서 실행하세요')

# ── ROS 2 ─────────────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from builtin_interfaces.msg import Time
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Image, Imu, Range
    from std_msgs.msg import Float64, Float32, Header, String
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print('[WARN] ROS 2 사용 불가 — rclpy 또는 메시지 패키지 없음')


# ==================================================================
# 로봇 물리 파라미터 (URDF + PROTO 기준)
# ==================================================================
WHEEL_SEPARATION = 0.30   # 좌우 바퀴 중심 간격 (m)
WHEEL_RADIUS = 0.04       # 바퀴 반지름 (m)
MAX_WHEEL_VELOCITY = 6.28 # rad/s

# 초음파 센서 이름 → ROS 토픽 매핑
US_SENSOR_MAP = {
    'us_front_center': '/ultrasonic/front_center',
    'us_front_left':   '/ultrasonic/front_left',
    'us_front_right':  '/ultrasonic/front_right',
    'us_left':         '/ultrasonic/left',
    'us_right':        '/ultrasonic/right',
}


class WebotsROS2Bridge:
    """Webots ↔ ROS 2 양방향 브릿지 (extern 모드 지원)"""

    def __init__(self):
        # ── Webots 초기화 ────────────────────────────────────
        if not WEBOTS_AVAILABLE:
            print('[ERROR] Webots controller 모듈 없음 — 종료')
            sys.exit(1)

        self.robot = WebotsRobot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # 모터 (속도 제어 모드)
        self.left_motor = self.robot.getDevice('left_wheel_motor')
        self.right_motor = self.robot.getDevice('right_wheel_motor')
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

        # 엔코더
        self.left_encoder = self.robot.getDevice('left_wheel_encoder')
        self.right_encoder = self.robot.getDevice('right_wheel_encoder')
        self.left_encoder.enable(self.timestep)
        self.right_encoder.enable(self.timestep)

        # 카메라 (2 스텝마다 = ~30fps at 16ms timestep)
        self.camera_front = self.robot.getDevice('camera_front')
        self.camera_front.enable(self.timestep * 2)
        self.camera_rear = self.robot.getDevice('camera_rear')
        self.camera_rear.enable(self.timestep * 2)

        # 깊이 카메라
        self.depth_front = self.robot.getDevice('depth_front')
        self.depth_front.enable(self.timestep * 2)

        # 초음파 x5
        self.us_sensors = {}
        for name in US_SENSOR_MAP:
            sensor = self.robot.getDevice(name)
            sensor.enable(self.timestep)
            self.us_sensors[name] = sensor

        # IMU
        self.imu = self.robot.getDevice('imu')
        self.imu.enable(self.timestep)
        self.gyro = self.robot.getDevice('gyro')
        self.gyro.enable(self.timestep)
        self.accel = self.robot.getDevice('accelerometer')
        self.accel.enable(self.timestep)

        # cmd_vel 상태
        self.target_linear_x = 0.0
        self.target_angular_z = 0.0
        self.last_cmd_time = 0.0
        self.frame_count = 0

        print(f'[INFO] Webots 디바이스 초기화 완료 (timestep={self.timestep}ms)')
        print(f'  wheel: sep={WHEEL_SEPARATION}m, radius={WHEEL_RADIUS}m')
        if os.environ.get('WEBOTS_CONTROLLER_URL'):
            print(f'  모드: EXTERN ({os.environ["WEBOTS_CONTROLLER_URL"]})')
        else:
            print('  모드: 내부 컨트롤러')

        # ── ROS 2 초기화 ────────────────────────────────────
        if not ROS2_AVAILABLE:
            print('[WARN] ROS 2 미사용 — 센서 데이터 로컬 출력만')
            self.node = None
            return

        rclpy.init(args=None)
        self.node = rclpy.create_node('webots_ros2_controller')

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Publishers
        self.pub_camera_front = self.node.create_publisher(
            Image, '/camera/front/image_raw', sensor_qos)
        self.pub_camera_rear = self.node.create_publisher(
            Image, '/camera/rear/image_raw', sensor_qos)
        self.pub_depth = self.node.create_publisher(
            Image, '/camera/depth/image_raw', sensor_qos)

        self.pub_us = {}
        for wb_name, topic in US_SENSOR_MAP.items():
            self.pub_us[wb_name] = self.node.create_publisher(Range, topic, sensor_qos)

        # 최소 초음파 거리 (safety_monitor/fsm_node용)
        self.pub_us_min = self.node.create_publisher(
            Float32, '/ultrasonic/min_distance', sensor_qos)

        self.pub_imu = self.node.create_publisher(Imu, '/imu/data', sensor_qos)
        self.pub_encoder_left = self.node.create_publisher(
            Float64, '/wheel/left/position', sensor_qos)
        self.pub_encoder_right = self.node.create_publisher(
            Float64, '/wheel/right/position', sensor_qos)

        # 하트비트 (watchdog_node용)
        self.pub_heartbeat = self.node.create_publisher(
            String, '/webots_controller/heartbeat', 10)
        self.heartbeat_timer = self.node.create_timer(1.0, self._publish_heartbeat)

        # Subscriber
        self.node.create_subscription(Twist, '/cmd_vel', self._cmd_vel_callback, 10)

        self.node.get_logger().info('WebotsROS2Bridge 준비 완료')

    # ==============================================================
    # 콜백
    # ==============================================================
    def _cmd_vel_callback(self, msg: 'Twist'):
        self.target_linear_x = msg.linear.x
        self.target_angular_z = msg.angular.z
        self.last_cmd_time = time.time()

    def _publish_heartbeat(self):
        msg = String()
        msg.data = 'alive'
        self.pub_heartbeat.publish(msg)

    # ==============================================================
    # 디퍼렌셜 드라이브
    # ==============================================================
    def _apply_cmd_vel(self):
        # 0.5초 타임아웃 → 정지
        if time.time() - self.last_cmd_time > 0.5:
            self.target_linear_x = 0.0
            self.target_angular_z = 0.0

        v_left = (
            (self.target_linear_x - self.target_angular_z * WHEEL_SEPARATION / 2.0)
            / WHEEL_RADIUS
        )
        v_right = (
            (self.target_linear_x + self.target_angular_z * WHEEL_SEPARATION / 2.0)
            / WHEEL_RADIUS
        )

        v_left = max(-MAX_WHEEL_VELOCITY, min(MAX_WHEEL_VELOCITY, v_left))
        v_right = max(-MAX_WHEEL_VELOCITY, min(MAX_WHEEL_VELOCITY, v_right))

        self.left_motor.setVelocity(v_left)
        self.right_motor.setVelocity(v_right)

    # ==============================================================
    # 타임스탬프
    # ==============================================================
    def _now_header(self, frame_id: str = 'base_link') -> 'Header':
        sim_time = self.robot.getTime()
        sec = int(sim_time)
        nanosec = int((sim_time - sec) * 1e9)
        header = Header()
        header.stamp = Time(sec=sec, nanosec=nanosec)
        header.frame_id = frame_id
        return header

    # ==============================================================
    # 센서 퍼블리시
    # ==============================================================
    def _publish_cameras(self):
        # 전면 RGB
        front_data = self.camera_front.getImage()
        if front_data:
            msg = Image()
            msg.header = self._now_header('camera_front_link')
            msg.width = self.camera_front.getWidth()
            msg.height = self.camera_front.getHeight()
            msg.encoding = 'bgra8'
            msg.step = msg.width * 4
            msg.is_bigendian = False
            msg.data = front_data
            self.pub_camera_front.publish(msg)

        # 후면 RGB
        rear_data = self.camera_rear.getImage()
        if rear_data:
            msg = Image()
            msg.header = self._now_header('camera_rear_link')
            msg.width = self.camera_rear.getWidth()
            msg.height = self.camera_rear.getHeight()
            msg.encoding = 'bgra8'
            msg.step = msg.width * 4
            msg.is_bigendian = False
            msg.data = rear_data
            self.pub_camera_rear.publish(msg)

        # 깊이
        depth_data = self.depth_front.getRangeImage()
        if depth_data:
            msg = Image()
            msg.header = self._now_header('depth_front_link')
            msg.width = self.depth_front.getWidth()
            msg.height = self.depth_front.getHeight()
            msg.encoding = '32FC1'
            msg.step = msg.width * 4
            msg.is_bigendian = False
            msg.data = struct.pack(f'{len(depth_data)}f', *depth_data)
            self.pub_depth.publish(msg)

    def _publish_ultrasonic(self):
        min_dist = float('inf')
        for wb_name, sensor in self.us_sensors.items():
            value = sensor.getValue()
            msg = Range()
            msg.header = self._now_header(f'{wb_name}_link')
            msg.radiation_type = Range.ULTRASOUND
            msg.field_of_view = 0.5236  # ~30 deg
            msg.min_range = 0.02
            msg.max_range = 2.0
            msg.range = float(value)
            self.pub_us[wb_name].publish(msg)
            if value < min_dist:
                min_dist = value

        # 최소 거리 퍼블리시 (FSM/안전 노드용)
        min_msg = Float32()
        min_msg.data = float(min_dist) if min_dist != float('inf') else 2.0
        self.pub_us_min.publish(min_msg)

    def _publish_imu(self):
        rpy = self.imu.getRollPitchYaw()
        gyro_vals = self.gyro.getValues()
        accel_vals = self.accel.getValues()

        msg = Imu()
        msg.header = self._now_header('imu_link')

        qx, qy, qz, qw = self._euler_to_quaternion(rpy[0], rpy[1], rpy[2])
        msg.orientation.x = qx
        msg.orientation.y = qy
        msg.orientation.z = qz
        msg.orientation.w = qw
        msg.orientation_covariance = [
            0.001, 0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 0.001,
        ]

        msg.angular_velocity.x = gyro_vals[0]
        msg.angular_velocity.y = gyro_vals[1]
        msg.angular_velocity.z = gyro_vals[2]
        msg.angular_velocity_covariance = [
            0.001, 0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 0.001,
        ]

        msg.linear_acceleration.x = accel_vals[0]
        msg.linear_acceleration.y = accel_vals[1]
        msg.linear_acceleration.z = accel_vals[2]
        msg.linear_acceleration_covariance = [
            0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.01,
        ]

        self.pub_imu.publish(msg)

    def _publish_encoders(self):
        left_msg = Float64()
        left_msg.data = self.left_encoder.getValue()
        self.pub_encoder_left.publish(left_msg)

        right_msg = Float64()
        right_msg.data = self.right_encoder.getValue()
        self.pub_encoder_right.publish(right_msg)

    # ==============================================================
    # 유틸
    # ==============================================================
    @staticmethod
    def _euler_to_quaternion(roll, pitch, yaw):
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        return (
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        )

    # ==============================================================
    # 메인 루프
    # ==============================================================
    def step(self) -> bool:
        if self.robot.step(self.timestep) == -1:
            return False

        self._apply_cmd_vel()

        if self.node is not None:
            self._publish_ultrasonic()
            self._publish_imu()
            self._publish_encoders()

            self.frame_count += 1
            if self.frame_count % 2 == 0:
                self._publish_cameras()

            rclpy.spin_once(self.node, timeout_sec=0)

        return True

    def cleanup(self):
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        if self.node is not None:
            self.node.destroy_node()
            rclpy.shutdown()
        print('[INFO] WebotsROS2Bridge 종료')


def main():
    if not WEBOTS_AVAILABLE:
        print('[ERROR] Webots controller 모듈 없음.')
        print()
        print('  # UTM Ubuntu에서 extern 모드로 실행하려면:')
        print('  pip3 install webots-controller')
        print('  export WEBOTS_CONTROLLER_URL=tcp://MAC_IP:1234/waste_robot')
        print('  python3 ros2_controller.py')
        print()
        print('  # 또는 CLI 인자로:')
        print('  python3 ros2_controller.py --url tcp://192.168.64.1:1234/waste_robot')
        sys.exit(1)

    bridge = WebotsROS2Bridge()
    print('[INFO] Webots ROS 2 브릿지 실행')

    try:
        while bridge.step():
            pass
    except KeyboardInterrupt:
        print('\n[INFO] 종료 중...')
    finally:
        bridge.cleanup()


if __name__ == '__main__':
    main()
