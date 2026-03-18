"""
Webots ROS 2 컨트롤러 — Webots 가상 센서/모터를 ROS 2 토픽과 연결한다.

역할:
  1. Webots 센서 데이터 → ROS 2 토픽 퍼블리시
  2. ROS 2 /cmd_vel → Webots 모터 속도 제어
  3. webots_ros2_driver가 아닌 수동 브릿지 (커스텀 제어 필요 시)

센서 → ROS 2:
  - realsense_color → /camera/color/image_raw
  - realsense_depth → /camera/depth/image_raw
  - rplidar_a1      → /scan
  - us_front/left/right/rear → /ultrasonic/ranges
  - imu + gyro + accel → /imu/data
  - left/right_wheel_encoder → /encoder/ticks

ROS 2 → 모터:
  - /cmd_vel → left_wheel_motor, right_wheel_motor

실행: Webots에서 이 파일을 컨트롤러로 지정
      또는 ros2 launch webots_ros2_driver robot_launch.py 사용
"""

# TODO: 아래는 webots_ros2_driver 사용 시의 기본 구조
# 실제 실행은 Ubuntu + ROS 2 Humble + Webots 설치 후

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import Image, LaserScan, Imu
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

        # --- 카메라 ---
        self.camera = self.robot.getDevice('realsense_color')
        self.camera.enable(self.timestep * 2)  # 30fps 정도

        # --- LiDAR ---
        self.lidar = self.robot.getDevice('rplidar_a1')
        self.lidar.enable(self.timestep)
        self.lidar.enablePointCloud()

        # --- 초음파 ---
        self.us_sensors = {}
        for name in ['us_front', 'us_left', 'us_right', 'us_rear']:
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

        # --- 로봇 파라미터 ---
        self.wheel_radius = 0.05   # 5cm
        self.wheel_base = 0.32     # 32cm (좌우 바퀴 간 거리)

        # --- 명령 속도 ---
        self.target_linear = 0.0
        self.target_angular = 0.0

        print('[INFO] WebotsROS2Controller 초기화 완료')

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

        # 디퍼렌셜 드라이브 계산
        left_vel = (self.target_linear - self.target_angular * self.wheel_base / 2.0) / self.wheel_radius
        right_vel = (self.target_linear + self.target_angular * self.wheel_base / 2.0) / self.wheel_radius

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
        }


def main():
    """
    메인 루프 — 2가지 실행 모드:
    1. Webots만 (ROS 2 없이): 센서 확인용 테스트
    2. Webots + ROS 2: webots_ros2_driver 또는 수동 브릿지
    """
    controller = WebotsROS2Controller()

    if not WEBOTS_AVAILABLE:
        print('[ERROR] Webots 환경 외부에서는 실행할 수 없습니다.')
        print('Webots에서 이 파일을 컨트롤러로 지정하거나,')
        print('ros2 launch webots_ros2_driver를 사용하세요.')
        return

    print('[INFO] Webots 시뮬레이션 시작')

    # TODO: ROS 2 노드 통합 시 rclpy.spin_once() 추가
    while controller.step():
        sensor_data = controller.get_sensor_data()
        # TODO: sensor_data를 ROS 2 토픽으로 퍼블리시
        pass

    print('[INFO] 시뮬레이션 종료')


if __name__ == '__main__':
    main()
