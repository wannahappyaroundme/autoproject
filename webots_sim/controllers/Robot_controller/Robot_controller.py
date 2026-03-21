"""
수거 로봇 컨트롤러 — 키보드 조작 + 초음파 장애물 회피

기능:
  - 방향키로 수동 조작 (UP/DOWN/LEFT/RIGHT)
  - 초음파 5개 센서로 실시간 장애물 감지
  - 로봇끼리 충돌 방지 (상대 로봇도 장애물로 인식)
  - 정지 상태에서 너무 가까운 물체 → 자동 후진
"""
from controller import Robot, Keyboard


class SmartGarbageController:

    US_NAMES = [
        'us_front_left', 'us_front_right',
        'us_side_left', 'us_side_right',
        'us_rear',
    ]

    # 거리 임계값 (미터, 초음파 최대 감지 1m)
    EMERGENCY = 0.20   # 긴급 정지 + 자동 후진
    CAUTION   = 0.45   # 감속 시작
    NOTICE    = 0.75   # 조향 보정 시작

    MAX_VEL   = 0.5    # 최대 직선 속도 (m/s)
    MAX_STEER = 0.45   # 최대 조향각 (rad)

    def __init__(self):
        self.robot = Robot()
        self.dt = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()

<<<<<<< HEAD
        # 2. 모터 연결 (PROTO에 새로 적은 이름과 똑같이 맞춤)
        # 앞바퀴 구동 모터
        self.left_motor = self.robot.getDevice('front_left_motor')
        self.right_motor = self.robot.getDevice('front_right_motor')
        self.left_motor.setPosition(float('inf')) # 속도 제어 모드
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)
        
        # 뒷바퀴 조향 모터
        self.steer_bl = self.robot.getDevice('steer_bl')
        self.steer_br = self.robot.getDevice('steer_br')
=======
        # --- 구동 모터 (후륜) ---
        self.lm = self.robot.getDevice('left_wheel_motor')
        self.rm = self.robot.getDevice('right_wheel_motor')
        self.lm.setPosition(float('inf'))
        self.rm.setPosition(float('inf'))
        self.lm.setVelocity(0)
        self.rm.setVelocity(0)
>>>>>>> 1dfb623ff3077b35e12f64da68958d562afaf695

        # --- 조향 모터 (전륜) ---
        self.sfl = self.robot.getDevice('steer_fl')
        self.sfr = self.robot.getDevice('steer_fr')

        # --- 초음파 센서 ---
        self.us = {}
        for n in self.US_NAMES:
            s = self.robot.getDevice(n)
            if s:
                s.enable(self.dt)
                self.us[n] = s

        # --- 카메라 (활성화만, 회피 로직에서는 미사용) ---
        for cn in ['realsense_color', 'webcam_color']:
            c = self.robot.getDevice(cn)
            if c:
                c.enable(self.dt * 4)

        # --- 엔코더 ---
        for en in ['left_wheel_encoder', 'right_wheel_encoder']:
            e = self.robot.getDevice(en)
            if e:
                e.enable(self.dt)

        # --- IMU ---
        imu = self.robot.getDevice('imu')
        if imu:
            imu.enable(self.dt)

        self.R = 0.04  # 바퀴 반경 (m)
        self.kb = Keyboard()
        self.kb.enable(self.dt)

        print(f'[{self.name}] 장애물 회피 컨트롤러 시작')

    # --------------------------------------------------
    def _dist(self, name):
        """초음파 센서값 → 거리(m). lookupTable [0→1000, 1m→0]"""
        s = self.us.get(name)
        if not s:
            return 999.0
        return max(0.0, 1.0 - s.getValue() / 1000.0)

    # --------------------------------------------------
    def run(self):
<<<<<<< HEAD
        print("🚀 컨트롤러가 정상적으로 시작되었습니다!")

        while self.robot.step(self.timestep) != -1:
            # 키보드 입력 처리 (다중 키 입력 지원)
            linear_speed = 0.0
            steering_angle = 0.0
            
            key = self.keyboard.getKey()
            while key != -1:
                if key == Keyboard.UP: linear_speed = 0.5  # 전진
                elif key == Keyboard.DOWN: linear_speed = -0.5
                if key == Keyboard.LEFT: steering_angle = -0.45 # 좌회전
                elif key == Keyboard.RIGHT: steering_angle = 0.45
                key = self.keyboard.getKey()

            # 5. 물리 계산 및 모터 명령 전달
            # 구동 속도 계산 (m/s -> rad/s)
            velocity = linear_speed / self.wheel_radius
            
            # 뒷바퀴 구동 적용
            self.left_motor.setVelocity(velocity)
            self.right_motor.setVelocity(velocity)
            
            # 앞바퀴 조향 적용 (Position 제어)
            self.steer_bl.setPosition(steering_angle)
            self.steer_br.setPosition(steering_angle)
            # 🔍 특정 센서 값 읽어오기
        
            # us_front_left 센서의 현재 값을 가져옵니다.
            val_fl = self.us_sensors['us_front_left'].getValue()
            val_fr = self.us_sensors['us_front_right'].getValue()
            val_sl = self.us_sensors['us_side_left'].getValue()
            val_sr = self.us_sensors['us_side_right'].getValue()
            val_rr = self.us_sensors['us_rear'].getValue()

            # 🖥️ 콘솔창에 출력 (f-string 사용)
            # .2f는 소수점 둘째 자리까지 표시하라는 뜻입니다.
            print(f"Front_L: {val_fl:.2f} | Front_R: {val_fr:.2f} | Side_L: {val_sl:.2f} | Side_R: {val_sr:.2f} | Rear: {val_rr:.2f}")
=======
        while self.robot.step(self.dt) != -1:

            # ── ① 키보드 입력 ──
            spd, steer = 0.0, 0.0
            k = self.kb.getKey()
            while k != -1:
                if   k == Keyboard.UP:    spd = self.MAX_VEL
                elif k == Keyboard.DOWN:  spd = -self.MAX_VEL
                if   k == Keyboard.LEFT:  steer = self.MAX_STEER
                elif k == Keyboard.RIGHT: steer = -self.MAX_STEER
                k = self.kb.getKey()

            # ── ② 초음파 읽기 ──
            fl   = self._dist('us_front_left')
            fr   = self._dist('us_front_right')
            sl   = self._dist('us_side_left')
            sr   = self._dist('us_side_right')
            rear = self._dist('us_rear')
            front = min(fl, fr)

            # ── ③ 전진 장애물 회피 ──
            if spd > 0:
                if front < self.EMERGENCY:
                    # 긴급 정지 + 반대 방향 조향
                    spd = 0.0
                    steer = -self.MAX_STEER if fl < fr else self.MAX_STEER

                elif front < self.CAUTION:
                    # 비례 감속
                    ratio = (front - self.EMERGENCY) / (self.CAUTION - self.EMERGENCY)
                    spd *= max(0.15, ratio)
                    # 가까운 쪽 반대로 조향 보정
                    if fl < fr:
                        steer -= 0.25
                    else:
                        steer += 0.25

                elif front < self.NOTICE:
                    # 부드러운 조향 보정
                    if fl < fr:
                        steer -= 0.12
                    elif fr < fl:
                        steer += 0.12

            # ── ④ 후진 장애물 회피 ──
            if spd < 0:
                if rear < self.EMERGENCY:
                    spd = 0.0
                elif rear < self.CAUTION:
                    ratio = (rear - self.EMERGENCY) / (self.CAUTION - self.EMERGENCY)
                    spd *= max(0.15, ratio)

            # ── ⑤ 측면 밀림 보정 ──
            if sl < self.EMERGENCY:
                steer -= 0.3   # 왼쪽 장애물 → 우회전
            if sr < self.EMERGENCY:
                steer += 0.3   # 오른쪽 장애물 → 좌회전

            # ── ⑥ 정지 상태 반응형 회피 ──
            #    아무 입력 없는데 앞에 장애물이 너무 가까우면 자동 후진
            if spd == 0.0 and steer == 0.0 and front < self.EMERGENCY:
                spd = -0.15

            # ── ⑦ 조향 범위 제한 ──
            steer = max(-self.MAX_STEER, min(self.MAX_STEER, steer))

            # ── ⑧ 모터 적용 ──
            vel = spd / self.R
            self.lm.setVelocity(vel)
            self.rm.setVelocity(vel)
            self.sfl.setPosition(steer)
            self.sfr.setPosition(steer)

>>>>>>> 1dfb623ff3077b35e12f64da68958d562afaf695

if __name__ == '__main__':
    SmartGarbageController().run()
