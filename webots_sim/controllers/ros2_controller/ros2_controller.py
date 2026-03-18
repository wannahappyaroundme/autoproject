"""
Webots ROS 2 컨트롤러 — Webots 가상 센서/모터를 ROS 2 토픽과 연결한다.

역할:
  1. Webots 센서 데이터 → ROS 2 토픽 퍼블리시
  2. ROS 2 /cmd_vel → Webots 모터 속도 제어
  3. webots_ros2_driver가 아닌 수동 브릿지 (커스텀 제어 필요 시)

센서 → ROS 2:
  - realsense_color  → /camera/realsense/color    (모드 B: SLAM)
  - realsense_depth  → /camera/realsense/depth     (모드 B: 장애물)
  - webcam_color     → /camera/webcam/color         (모드 A: QR/정렬)
  - us_front_left/front_right/side_left/side_right/rear → /ultrasonic/ranges
  - imu + gyro + accel → /imu/data
  - left/right_wheel_encoder → /encoder/ticks

ROS 2 → 모터:
  - /cmd_vel → left_wheel_motor, right_wheel_motor

실행: Webots에서 이 파일을 컨트롤러로 지정
      또는 ros2 launch webots_ros2_driver robot_launch.py 사용
"""

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Image, Imu
    from std_msgs.msg import String
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False

try:
    from controller import Robot as WebotsRobot
    WEBOTS_AVAILABLE = True
except ImportError:
    WEBOTS_AVAILABLE = False


class WebotsROS2Controller:
    """Webots ↔ ROS 2 브릿지 컨트롤러"""

    # 초음파 센서 이름 (하드웨어 명세서 기준 5개)
    US_SENSORS = ['us_front_left', 'us_front_right', 'us_side_left', 'us_side_right', 'us_rear']

    def __init__(self):
        if not WEBOTS_AVAILABLE:
            print('[WARN] Webots controller 모듈 없음 — 시뮬레이션 외부에서 실행됨')
            return

        self.robot = WebotsRobot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # --- 모터 ---
        self.left_motor = self.robot.getDevice('left_wheel_motor')
        self.right_motor = self.robot.getDevice('right_wheel_motor')
        self.left_motor.setPosition(float('inf'))  # 속도 제어 모드
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

        # --- 엔코더 ---
        self.left_encoder = self.robot.getDevice('left_wheel_encoder')
        self.right_encoder = self.robot.getDevice('right_wheel_encoder')
        self.left_encoder.enable(self.timestep)
        self.right_encoder.enable(self.timestep)

        # --- 카메라 B: RealSense D435 (후면 외측 — SLAM/Depth) ---
        self.realsense_color = self.robot.getDevice('realsense_color')
        self.realsense_color.enable(self.timestep * 2)  # ~30fps
        self.realsense_depth = self.robot.getDevice('realsense_depth')
        self.realsense_depth.enable(self.timestep * 2)

        # --- 카메라 A: USB 웹캠 (후면 내측 — QR/Visual Servoing) ---
        self.webcam = self.robot.getDevice('webcam_color')
        self.webcam.enable(self.timestep * 2)

        # --- 초음파 × 5 ---
        self.us_sensors = {}
        for name in self.US_SENSORS:
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

        # --- 로봇 파라미터 (하드웨어 명세서 기준) ---
        self.wheel_radius = 0.04   # 80mm 바퀴 → 반지름 40mm
        self.wheel_base = 0.32     # 32cm (좌우 바퀴 간 거리)

        # --- 명령 속도 ---
        self.target_linear = 0.0
        self.target_angular = 0.0

        # --- 현재 모드 ---
        self.mode = 'B'  # A=전진접근, B=후진운반 (기본 B로 시작)

        print('[INFO] WebotsROS2Controller 초기화 완료')
        print(f'  카메라: RealSense D435 + USB 웹캠')
        print(f'  초음파: {len(self.US_SENSORS)}개 (FL, FR, SL, SR, R)')
        print(f'  LiDAR: 없음 (Visual SLAM 사용)')

    def cmd_vel_callback(self, linear_x: float, angular_z: float):
        """Twist → 좌우 바퀴 속도 변환 (differential drive)"""
        self.target_linear = linear_x
        self.target_angular = angular_z

    def step(self):
        """매 시뮬레이션 스텝마다 호출"""
        if not WEBOTS_AVAILABLE:
            return False

        if self.robot.step(self.timestep) == -1:
            return False

        # 모드에 따라 모터 부호 반전 (모드 B = 후진이 전방)
        sign = -1.0 if self.mode == 'B' else 1.0

        left_vel = sign * (self.target_linear - self.target_angular * self.wheel_base / 2.0) / self.wheel_radius
        right_vel = sign * (self.target_linear + self.target_angular * self.wheel_base / 2.0) / self.wheel_radius

        self.left_motor.setVelocity(left_vel)
        self.right_motor.setVelocity(right_vel)

        return True

    def get_sensor_data(self) -> dict:
        """현재 센서 데이터 반환"""
        return {
            'encoders': {
                'left': self.left_encoder.getValue(),
                'right': self.right_encoder.getValue(),
            },
            'ultrasonic': {
                name: sensor.getValue()
                for name, sensor in self.us_sensors.items()
            },
            'imu': {
                'roll_pitch_yaw': list(self.imu.getRollPitchYaw()),
                'gyro': list(self.gyro.getValues()),
                'accel': list(self.accel.getValues()),
            },
            'mode': self.mode,
        }

    def get_depth_pointcloud(self):
        """RealSense depth → 2D 장애물 정보 (Nav2 costmap용)"""
        if not WEBOTS_AVAILABLE:
            return None
        depth_image = self.realsense_depth.getRangeImage()
        width = self.realsense_depth.getWidth()
        height = self.realsense_depth.getHeight()
        return {
            'data': depth_image,
            'width': width,
            'height': height,
            'min_range': 0.1,
            'max_range': 10.0,
        }


def main():
    controller = WebotsROS2Controller()

    if not WEBOTS_AVAILABLE:
        print('[ERROR] Webots 환경 외부에서는 실행할 수 없습니다.')
        return

    print('[INFO] Webots 시뮬레이션 시작')

    while controller.step():
        sensor_data = controller.get_sensor_data()
        # TODO: sensor_data를 ROS 2 토픽으로 퍼블리시
        # TODO: depth_pointcloud → /camera/realsense/depth/points


if __name__ == '__main__':
    main()
