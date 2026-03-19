"""
Webots ROS 2 컨트롤러 — Webots 센서/모터를 ROS 2 토픽과 양방향 연결한다.

아키텍처:
  Webots 시뮬레이션 (센서/모터)
       |
  ros2_controller.py (이 파일)
       |
  ROS 2 토픽 (/cmd_vel, /camera/*, /ultrasonic/*, /imu/*, /wheel/*)
       |
  기존 ROS 2 노드들 (navigation_node, mission_manager, ...)

퍼블리시 토픽 (Webots -> ROS 2):
  /camera/front/image_raw      sensor_msgs/Image          전면 RGB (640x480)
  /camera/rear/image_raw       sensor_msgs/Image          후면 RGB (640x480)
  /camera/depth/image_raw      sensor_msgs/Image          깊이 (640x480, 32FC1)
  /ultrasonic/front_center     sensor_msgs/Range          전방 중앙 초음파
  /ultrasonic/front_left       sensor_msgs/Range          전방 좌측 초음파
  /ultrasonic/front_right      sensor_msgs/Range          전방 우측 초음파
  /ultrasonic/left             sensor_msgs/Range          좌측 초음파
  /ultrasonic/right            sensor_msgs/Range          우측 초음파
  /imu/data                    sensor_msgs/Imu            IMU (가속도+자이로+방향)
  /wheel/left/position         std_msgs/Float64           좌측 엔코더
  /wheel/right/position        std_msgs/Float64           우측 엔코더

구독 토픽 (ROS 2 -> Webots):
  /cmd_vel                     geometry_msgs/Twist        속도 명령 -> 디퍼렌셜 구동

로봇 파라미터 (URDF 기준):
  wheel_separation = 0.30m  (좌우 바퀴 중심 간격)
  wheel_radius     = 0.04m  (바퀴 반지름 40mm)

실행:
  Webots world 파일에서 controller "ros2_controller" 로 지정
  또는 launch 파일에서 webots_ros2_driver로 실행
"""

import math
import struct
import sys
import time

# ---- Webots controller API ----
try:
    from controller import Robot as WebotsRobot
    WEBOTS_AVAILABLE = True
except ImportError:
    WEBOTS_AVAILABLE = False

# ---- ROS 2 ----
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from builtin_interfaces.msg import Time
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Image, Imu, Range
    from std_msgs.msg import Float64, Header
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


# ==================================================================
# 로봇 물리 파라미터 (URDF waste_robot.urdf.xacro 기준)
# ==================================================================
WHEEL_SEPARATION = 0.30   # 좌우 바퀴 중심 간격 (m)
WHEEL_RADIUS = 0.04       # 바퀴 반지름 (m)
MAX_WHEEL_VELOCITY = 6.28 # rad/s (RotationalMotor maxVelocity)

# 초음파 센서 이름 -> ROS 토픽 매핑
US_SENSOR_MAP = {
    'us_front_center': '/ultrasonic/front_center',
    'us_front_left':   '/ultrasonic/front_left',
    'us_front_right':  '/ultrasonic/front_right',
    'us_left':         '/ultrasonic/left',
    'us_right':        '/ultrasonic/right',
}


class WebotsROS2Bridge:
    """Webots <-> ROS 2 양방향 브릿지"""

    def __init__(self):
        # ----------------------------------------------------------
        # Webots 초기화
        # ----------------------------------------------------------
        if not WEBOTS_AVAILABLE:
            print('[ERROR] Webots controller 모듈 없음')
            sys.exit(1)

        self.robot = WebotsRobot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # --- 모터 (속도 제어 모드) ---
        self.left_motor = self.robot.getDevice('left_wheel_motor')
        self.right_motor = self.robot.getDevice('right_wheel_motor')
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

        # --- 엔코더 ---
        self.left_encoder = self.robot.getDevice('left_wheel_encoder')
        self.right_encoder = self.robot.getDevice('right_wheel_encoder')
        self.left_encoder.enable(self.timestep)
        self.right_encoder.enable(self.timestep)

        # --- 카메라 ---
        self.camera_front = self.robot.getDevice('camera_front')
        self.camera_front.enable(self.timestep * 2)  # ~30fps at 16ms timestep

        self.camera_rear = self.robot.getDevice('camera_rear')
        self.camera_rear.enable(self.timestep * 2)

        # --- 깊이 카메라 (RangeFinder) ---
        self.depth_front = self.robot.getDevice('depth_front')
        self.depth_front.enable(self.timestep * 2)

        # --- 초음파 센서 x5 ---
        self.us_sensors = {}
        for name in US_SENSOR_MAP:
            sensor = self.robot.getDevice(name)
            sensor.enable(self.timestep)
            self.us_sensors[name] = sensor

        # --- IMU ---
        self.imu = self.robot.getDevice('imu')
        self.imu.enable(self.timestep)
        self.gyro = self.robot.getDevice('gyro')
        self.gyro.enable(self.timestep)
        self.accel = self.robot.getDevice('accelerometer')
        self.accel.enable(self.timestep)

        # --- 목표 속도 (cmd_vel에서 갱신) ---
        self.target_linear_x = 0.0
        self.target_angular_z = 0.0
        self.last_cmd_time = 0.0

        # --- 프레임 카운터 (카메라는 2 스텝마다 퍼블리시) ---
        self.frame_count = 0

        print('[INFO] Webots 디바이스 초기화 완료')
        print(f'  timestep: {self.timestep}ms')
        print(f'  wheel_separation: {WHEEL_SEPARATION}m, wheel_radius: {WHEEL_RADIUS}m')

        # ----------------------------------------------------------
        # ROS 2 초기화
        # ----------------------------------------------------------
        if not ROS2_AVAILABLE:
            print('[WARN] ROS 2 사용 불가 — 센서 데이터는 로컬 출력만')
            self.node = None
            return

        rclpy.init(args=None)
        self.node = rclpy.create_node('webots_ros2_controller')

        # QoS: 센서 데이터는 best-effort, 소량 히스토리
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # --- Publishers ---
        self.pub_camera_front = self.node.create_publisher(
            Image, '/camera/front/image_raw', sensor_qos)
        self.pub_camera_rear = self.node.create_publisher(
            Image, '/camera/rear/image_raw', sensor_qos)
        self.pub_depth = self.node.create_publisher(
            Image, '/camera/depth/image_raw', sensor_qos)

        self.pub_us = {}
        for wb_name, topic in US_SENSOR_MAP.items():
            self.pub_us[wb_name] = self.node.create_publisher(
                Range, topic, sensor_qos)

        self.pub_imu = self.node.create_publisher(
            Imu, '/imu/data', sensor_qos)
        self.pub_encoder_left = self.node.create_publisher(
            Float64, '/wheel/left/position', sensor_qos)
        self.pub_encoder_right = self.node.create_publisher(
            Float64, '/wheel/right/position', sensor_qos)

        # --- Subscriber ---
        self.node.create_subscription(
            Twist, '/cmd_vel', self._cmd_vel_callback, 10)

        self.node.get_logger().info(
            'WebotsROS2Bridge 준비 완료 — 퍼블리시/구독 시작')

    # ==============================================================
    # cmd_vel 콜백
    # ==============================================================
    def _cmd_vel_callback(self, msg: 'Twist'):
        """ROS 2 /cmd_vel -> 목표 속도 저장"""
        self.target_linear_x = msg.linear.x
        self.target_angular_z = msg.angular.z
        self.last_cmd_time = time.time()

    # ==============================================================
    # Differential Drive 변환
    # ==============================================================
    def _apply_cmd_vel(self):
        """target_linear_x, target_angular_z -> 좌/우 바퀴 각속도"""
        # cmd_vel 타임아웃 (0.5초 이상 수신 없으면 정지)
        if time.time() - self.last_cmd_time > 0.5:
            self.target_linear_x = 0.0
            self.target_angular_z = 0.0

        # 디퍼렌셜 드라이브 공식:
        #   v_left  = (linear - angular * separation / 2) / radius
        #   v_right = (linear + angular * separation / 2) / radius
        v_left = (
            (self.target_linear_x - self.target_angular_z * WHEEL_SEPARATION / 2.0)
            / WHEEL_RADIUS
        )
        v_right = (
            (self.target_linear_x + self.target_angular_z * WHEEL_SEPARATION / 2.0)
            / WHEEL_RADIUS
        )

        # 클램핑
        v_left = max(-MAX_WHEEL_VELOCITY, min(MAX_WHEEL_VELOCITY, v_left))
        v_right = max(-MAX_WHEEL_VELOCITY, min(MAX_WHEEL_VELOCITY, v_right))

        self.left_motor.setVelocity(v_left)
        self.right_motor.setVelocity(v_right)

    # ==============================================================
    # 타임스탬프 헬퍼
    # ==============================================================
    def _now_header(self, frame_id: str = 'base_link') -> 'Header':
        """현재 시뮬레이션 시간 기반 Header 생성"""
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
        """전면/후면 RGB + 깊이 카메라 이미지 퍼블리시"""
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

        # 깊이 카메라
        depth_data = self.depth_front.getRangeImage()
        if depth_data:
            msg = Image()
            msg.header = self._now_header('depth_front_link')
            msg.width = self.depth_front.getWidth()
            msg.height = self.depth_front.getHeight()
            msg.encoding = '32FC1'
            msg.step = msg.width * 4
            msg.is_bigendian = False
            # RangeFinder returns list of floats -> pack to bytes
            msg.data = struct.pack(f'{len(depth_data)}f', *depth_data)
            self.pub_depth.publish(msg)

    def _publish_ultrasonic(self):
        """초음파 센서 5개 Range 메시지 퍼블리시"""
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

    def _publish_imu(self):
        """IMU 데이터 (InertialUnit + Gyro + Accelerometer) 퍼블리시"""
        rpy = self.imu.getRollPitchYaw()       # [roll, pitch, yaw]
        gyro_vals = self.gyro.getValues()       # [wx, wy, wz]
        accel_vals = self.accel.getValues()     # [ax, ay, az]

        msg = Imu()
        msg.header = self._now_header('imu_link')

        # 방향 (roll/pitch/yaw -> quaternion)
        qx, qy, qz, qw = self._euler_to_quaternion(rpy[0], rpy[1], rpy[2])
        msg.orientation.x = qx
        msg.orientation.y = qy
        msg.orientation.z = qz
        msg.orientation.w = qw
        msg.orientation_covariance = [
            0.001, 0.0, 0.0,
            0.0, 0.001, 0.0,
            0.0, 0.0, 0.001,
        ]

        # 각속도
        msg.angular_velocity.x = gyro_vals[0]
        msg.angular_velocity.y = gyro_vals[1]
        msg.angular_velocity.z = gyro_vals[2]
        msg.angular_velocity_covariance = [
            0.001, 0.0, 0.0,
            0.0, 0.001, 0.0,
            0.0, 0.0, 0.001,
        ]

        # 선가속도
        msg.linear_acceleration.x = accel_vals[0]
        msg.linear_acceleration.y = accel_vals[1]
        msg.linear_acceleration.z = accel_vals[2]
        msg.linear_acceleration_covariance = [
            0.01, 0.0, 0.0,
            0.0, 0.01, 0.0,
            0.0, 0.0, 0.01,
        ]

        self.pub_imu.publish(msg)

    def _publish_encoders(self):
        """바퀴 엔코더 위치값 퍼블리시"""
        left_msg = Float64()
        left_msg.data = self.left_encoder.getValue()
        self.pub_encoder_left.publish(left_msg)

        right_msg = Float64()
        right_msg.data = self.right_encoder.getValue()
        self.pub_encoder_right.publish(right_msg)

    # ==============================================================
    # 유틸리티
    # ==============================================================
    @staticmethod
    def _euler_to_quaternion(roll: float, pitch: float, yaw: float):
        """오일러각(RPY) -> 쿼터니언(x, y, z, w) 변환"""
        cr = math.cos(roll / 2.0)
        sr = math.sin(roll / 2.0)
        cp = math.cos(pitch / 2.0)
        sp = math.sin(pitch / 2.0)
        cy = math.cos(yaw / 2.0)
        sy = math.sin(yaw / 2.0)

        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
        return qx, qy, qz, qw

    # ==============================================================
    # 메인 루프
    # ==============================================================
    def step(self) -> bool:
        """매 시뮬레이션 스텝 실행. False 반환 시 종료."""
        if self.robot.step(self.timestep) == -1:
            return False

        # 모터 제어
        self._apply_cmd_vel()

        # ROS 2 퍼블리시
        if self.node is not None:
            # 매 스텝: 초음파, IMU, 엔코더 (빠른 업데이트 필요)
            self._publish_ultrasonic()
            self._publish_imu()
            self._publish_encoders()

            # 2 스텝마다: 카메라 (대역폭 절감)
            self.frame_count += 1
            if self.frame_count % 2 == 0:
                self._publish_cameras()

            # ROS 2 콜백 처리
            rclpy.spin_once(self.node, timeout_sec=0)

        return True

    def cleanup(self):
        """종료 시 정리"""
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        if self.node is not None:
            self.node.destroy_node()
            rclpy.shutdown()
        print('[INFO] WebotsROS2Bridge 종료')


def main():
    """메인 진입점 — Webots 컨트롤러로 실행"""
    if not WEBOTS_AVAILABLE:
        print('[ERROR] Webots 환경 외부에서는 실행할 수 없습니다.')
        print('  이 스크립트는 Webots 시뮬레이터 내부에서 컨트롤러로 실행됩니다.')
        sys.exit(1)

    bridge = WebotsROS2Bridge()
    print('[INFO] Webots ROS 2 브릿지 실행 시작')
    print('[INFO] /cmd_vel 구독 대기 중...')

    try:
        while bridge.step():
            pass
    except KeyboardInterrupt:
        print('[INFO] 키보드 인터럽트 — 종료 중...')
    finally:
        bridge.cleanup()


if __name__ == '__main__':
    main()
