from controller import Robot, Keyboard

class WebotsROS2Controller:
    # 1. 경석님 하드웨어 명세서의 초음파 센서 리스트
    US_SENSORS = ['us_front_left', 'us_front_right', 'us_side_left', 'us_side_right', 'us_rear']

    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # 2. 모터 연결 (PROTO에 새로 적은 이름과 똑같이 맞춤)
        # 뒷바퀴 구동 모터
        self.left_motor = self.robot.getDevice('left_wheel_motor')
        self.right_motor = self.robot.getDevice('right_wheel_motor')
        self.left_motor.setPosition(float('inf')) # 속도 제어 모드
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        
        # 앞바퀴 조향 모터
        self.steer_fl = self.robot.getDevice('steer_fl')
        self.steer_fr = self.robot.getDevice('steer_fr')

        # 3. 센서 활성화 (경석님 소프트웨어 사양 반영)
        # 카메라 A (웹캠) 및 카메라 B (리얼센스)
        self.realsense_color = self.robot.getDevice('realsense_color')
        if self.realsense_color: self.realsense_color.enable(self.timestep * 2)
        
        self.webcam = self.robot.getDevice('webcam_color')
        if self.webcam: self.webcam.enable(self.timestep * 2)

        # 초음파 센서 5개 활성화
        self.us_sensors = {name: self.robot.getDevice(name) for name in self.US_SENSORS}
        for s in self.us_sensors.values():
            if s: s.enable(self.timestep)

        # IMU(관성 센서) 활성화
        self.imu = self.robot.getDevice('imu')
        if self.imu: self.imu.enable(self.timestep)

        # 4. 제어 파라미터 (80mm 바퀴 기준)
        self.wheel_radius = 0.04 
        self.keyboard = Keyboard()
        self.keyboard.enable(self.timestep)

    def run(self):
        while self.robot.step(self.timestep) != -1:
            # 키보드 입력 처리 (다중 키 입력 지원)
            linear_speed = 0.0
            steering_angle = 0.0
            
            key = self.keyboard.getKey()
            while key != -1:
                if key == Keyboard.UP: linear_speed = 0.5  # 전진
                elif key == Keyboard.DOWN: linear_speed = -0.5
                if key == Keyboard.LEFT: steering_angle = 0.45 # 좌회전
                elif key == Keyboard.RIGHT: steering_angle = -0.45
                key = self.keyboard.getKey()

            # 5. 물리 계산 및 모터 명령 전달
            # 구동 속도 계산 (m/s -> rad/s)
            velocity = linear_speed / self.wheel_radius
            
            # 뒷바퀴 구동 적용
            self.left_motor.setVelocity(velocity)
            self.right_motor.setVelocity(velocity)
            
            # 앞바퀴 조향 적용 (Position 제어)
            self.steer_fl.setPosition(steering_angle)
            self.steer_fr.setPosition(steering_angle)

if __name__ == '__main__':
    controller = WebotsROS2Controller()
    controller.run()