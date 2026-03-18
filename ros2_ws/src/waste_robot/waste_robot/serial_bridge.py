"""
시리얼 브릿지 — Jetson Orin Nano ↔ Arduino Mega UART 통신을 담당한다.

역할:
  1. ROS 2 토픽 → Arduino 명령 변환 (CMD 프로토콜)
  2. Arduino 센서 데이터 → ROS 2 토픽 변환 (DATA 프로토콜)

프로토콜 (하드웨어 명세서 Section 10 참조):
  Jetson → Arduino: CMD,<type>,<val1>,<val2>\n
    - CMD,DRIVE,<left_rpm>,<right_rpm>
    - CMD,STEER,<angle_deg>,0
    - CMD,ROLLER,<action>,0          (action: GRAB | RELEASE | STOP)
    - CMD,STOP,0,0

  Arduino → Jetson: DATA,<type>,<values>\n
    - DATA,ENC,<left_tick>,<right_tick>
    - DATA,IMU,<yaw>,<pitch>,<roll>
    - DATA,USS,<front_cm>,<left_cm>,<right_cm>,<rear_cm>
    - DATA,BAT,<voltage>,<percentage>
    - DATA,ROLLER,<state>             (state: GRABBED | RELEASED | MOVING)

토픽:
  - /cmd_vel (sub)           : 속도 명령 → CMD,DRIVE로 변환
  - /roller/command (sub)    : 롤러 파지 명령 → CMD,ROLLER로 변환
  - /encoder/ticks (pub)     : 엔코더 틱 데이터
  - /imu/raw (pub)           : IMU yaw/pitch/roll
  - /ultrasonic/ranges (pub) : 초음파 4방향 거리
  - /battery/state (pub)     : 배터리 전압/잔량
  - /roller/state (pub)      : 롤러 현재 상태

실행: ros2 run waste_robot serial_bridge
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from geometry_msgs.msg import Twist

# TODO: 실제 실행 시 아래 import 활성화
# import serial


class SerialBridge(Node):
    def __init__(self):
        super().__init__('serial_bridge')

        # --- 파라미터 ---
        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baud', 115200)
        port = self.get_parameter('port').value
        baud = self.get_parameter('baud').value

        # --- 시리얼 포트 ---
        # TODO: 실제 실행 시 활성화
        # self.ser = serial.Serial(port, baud, timeout=0.01)
        self.ser = None
        self.get_logger().info(f'시리얼 포트: {port} @ {baud}bps')

        # --- Publishers (Arduino → ROS 2) ---
        self.enc_pub = self.create_publisher(String, '/encoder/ticks', 10)
        self.imu_pub = self.create_publisher(String, '/imu/raw', 10)
        self.uss_pub = self.create_publisher(String, '/ultrasonic/ranges', 10)
        self.bat_pub = self.create_publisher(String, '/battery/state', 10)
        self.roller_state_pub = self.create_publisher(String, '/roller/state', 10)

        # --- Subscribers (ROS 2 → Arduino) ---
        self.cmd_vel_sub = self.create_subscription(
            Twist, '/cmd_vel', self.on_cmd_vel, 10
        )
        self.roller_cmd_sub = self.create_subscription(
            String, '/roller/command', self.on_roller_command, 10
        )

        # 50Hz로 시리얼 읽기
        self.timer = self.create_timer(0.02, self.read_serial)

        self.get_logger().info('SerialBridge 시작됨')

    def on_cmd_vel(self, msg: Twist):
        """Twist → CMD,DRIVE,<left_rpm>,<right_rpm>"""
        # TODO: Twist → 좌우 RPM 변환 (로봇 폭, 바퀴 반지름 기반)
        linear = msg.linear.x
        angular = msg.angular.z
        wheel_base = 0.30  # 30cm (하드웨어 명세서 기준)
        left_vel = linear - (angular * wheel_base / 2.0)
        right_vel = linear + (angular * wheel_base / 2.0)

        # 속도 → RPM 변환 (바퀴 반지름 0.05m 기준)
        wheel_radius = 0.05
        left_rpm = int((left_vel / (2 * 3.14159 * wheel_radius)) * 60)
        right_rpm = int((right_vel / (2 * 3.14159 * wheel_radius)) * 60)

        self.send_command(f'CMD,DRIVE,{left_rpm},{right_rpm}')

    def on_roller_command(self, msg: String):
        """롤러 명령: GRAB | RELEASE | STOP"""
        action = msg.data.upper()
        if action in ('GRAB', 'RELEASE', 'STOP'):
            self.send_command(f'CMD,ROLLER,{action},0')

    def send_command(self, cmd: str):
        """Arduino로 명령 전송"""
        if self.ser:
            self.ser.write(f'{cmd}\n'.encode())
        self.get_logger().debug(f'TX: {cmd}')

    def read_serial(self):
        """Arduino로부터 데이터 수신 (50Hz)"""
        if not self.ser:
            return

        # TODO: 실제 구현
        # while self.ser.in_waiting:
        #     line = self.ser.readline().decode().strip()
        #     if not line.startswith('DATA,'):
        #         continue
        #     parts = line.split(',')
        #     dtype = parts[1]
        #
        #     msg = String()
        #     msg.data = line
        #
        #     if dtype == 'ENC':
        #         self.enc_pub.publish(msg)
        #     elif dtype == 'IMU':
        #         self.imu_pub.publish(msg)
        #     elif dtype == 'USS':
        #         self.uss_pub.publish(msg)
        #     elif dtype == 'BAT':
        #         self.bat_pub.publish(msg)
        #     elif dtype == 'ROLLER':
        #         self.roller_state_pub.publish(msg)
        pass


def main(args=None):
    rclpy.init(args=args)
    node = SerialBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
