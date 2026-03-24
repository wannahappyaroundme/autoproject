"""
고정 경로 순찰 컨트롤러 — 보행자/자동차/자전거 등 동적 장애물용
로봇 이름에 따라 경로와 속도가 결정됨.
"""
from controller import Robot
import math

# ── 순찰 경로 (월드 좌표 웨이포인트) ──
# 맵: 200×140 그리드, world_x = gx*2-200, world_y = 140-gy*2

ROUTES = {
    # ═══ 차량 7대 (도로 주행) ═══
    "Car_1": {"speed": 1.2, "waypoints": [  # N-S 중앙로 북→남
        (-1, 120), (-1, 60), (-1, 0), (-1, -60), (-1, -120),
        (-1, -60), (-1, 0), (-1, 60)]},
    "Car_2": {"speed": 1.0, "waypoints": [  # E-W 횡단로 서→동
        (-180, 2), (-120, 2), (-60, 2), (0, 2), (60, 2), (120, 2), (180, 2),
        (120, 2), (60, 2), (0, 2), (-60, 2), (-120, 2)]},
    "Car_3": {"speed": 0.8, "waypoints": [  # NW 구역 순회
        (-180, 60), (-100, 60), (-100, 120), (-180, 120)]},
    "Car_4": {"speed": 0.9, "waypoints": [  # NE 구역 순회
        (60, 60), (160, 60), (160, 120), (60, 120)]},
    "Car_5": {"speed": 0.85, "waypoints": [  # SW 구역 순회
        (-180, -40), (-100, -40), (-100, -120), (-180, -120)]},
    "Car_6": {"speed": 0.95, "waypoints": [  # SE 구역 순회
        (60, -40), (160, -40), (160, -120), (60, -120)]},
    "Car_7": {"speed": 1.1, "waypoints": [  # 단지 외곽 대순환
        (-180, 130), (180, 130), (180, -130), (-180, -130)]},
    # ═══ 보행자 15명 (건물 사이 산책) ═══
    "Ped_1":  {"speed": 0.40, "waypoints": [(-160, 100), (-120, 100), (-120, 60), (-160, 60)]},
    "Ped_2":  {"speed": 0.35, "waypoints": [(-60, 70), (-40, 70), (-40, 50), (-60, 50)]},
    "Ped_3":  {"speed": 0.45, "waypoints": [(80, -40), (140, -40), (140, -100), (80, -100)]},
    "Ped_4":  {"speed": 0.30, "waypoints": [(-20, 20), (20, 20), (20, -20), (-20, -20)]},
    "Ped_5":  {"speed": 0.40, "waypoints": [(60, 100), (120, 100), (120, 50), (60, 50)]},
    "Ped_6":  {"speed": 0.38, "waypoints": [(-140, 40), (-80, 40), (-80, 20), (-140, 20)]},
    "Ped_7":  {"speed": 0.42, "waypoints": [(-170, -60), (-110, -60), (-110, -100), (-170, -100)]},
    "Ped_8":  {"speed": 0.36, "waypoints": [(100, 80), (160, 80), (160, 40), (100, 40)]},
    "Ped_9":  {"speed": 0.33, "waypoints": [(70, -70), (150, -70), (150, -110), (70, -110)]},
    "Ped_10": {"speed": 0.40, "waypoints": [(-10, 80), (-10, 40), (10, 40), (10, 80)]},
    "Ped_11": {"speed": 0.37, "waypoints": [(-150, -20), (-100, -20), (-100, -50), (-150, -50)]},
    "Ped_12": {"speed": 0.44, "waypoints": [(40, 30), (90, 30), (90, -10), (40, -10)]},
    "Ped_13": {"speed": 0.32, "waypoints": [(-50, -80), (-20, -80), (-20, -110), (-50, -110)]},
    "Ped_14": {"speed": 0.41, "waypoints": [(110, 10), (170, 10), (170, -20), (110, -20)]},
    "Ped_15": {"speed": 0.38, "waypoints": [(-80, 110), (-40, 110), (-40, 80), (-80, 80)]},
    # ═══ 자전거 4대 (도로 빠른 이동) ═══
    "Bike_1": {"speed": 1.8, "waypoints": [(-8, 120), (-8, 0), (-8, -120), (-8, 0)]},
    "Bike_2": {"speed": 1.6, "waypoints": [(8, -120), (8, 0), (8, 120), (8, 0)]},
    "Bike_3": {"speed": 1.7, "waypoints": [(-180, 8), (0, 8), (180, 8), (0, 8)]},
    "Bike_4": {"speed": 1.5, "waypoints": [(180, -6), (0, -6), (-180, -6), (0, -6)]},
}

# ── 기본 경로 (이름이 목록에 없으면) ──
DEFAULT_ROUTE = {
    "speed": 0.3,
    "waypoints": [(0, 50), (50, 0), (0, -50), (-50, 0), (0, 50)],
}

ARRIVE_THRESHOLD = 2.0  # 웨이포인트 도달 판정 (m)


class PatrolController:
    def __init__(self):
        self.robot = Robot()
        self.dt = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()

        # 모터 (differential drive)
        self.left_motor = self.robot.getDevice('left_wheel')
        self.right_motor = self.robot.getDevice('right_wheel')
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0)
        self.right_motor.setVelocity(0)

        # GPS & Compass
        self.gps = self.robot.getDevice('gps')
        self.gps.enable(self.dt)
        self.compass = self.robot.getDevice('compass')
        self.compass.enable(self.dt)

        # 경로 설정
        route = ROUTES.get(self.name, DEFAULT_ROUTE)
        self.max_speed = route["speed"]
        self.waypoints = route["waypoints"]
        self.wp_idx = 0
        self.wheel_radius = 0.03
        self.axle_length = 0.3

        print(f'[{self.name}] 순찰 시작 — {len(self.waypoints)}개 웨이포인트, 속도 {self.max_speed}m/s')

    def get_pos(self):
        v = self.gps.getValues()
        if math.isnan(v[0]) or math.isnan(v[1]):
            return 0.0, 0.0
        return v[0], v[1]

    def get_heading(self):
        v = self.compass.getValues()
        return math.atan2(v[0], v[1])

    def run(self):
        # GPS 초기화 대기
        for _ in range(5):
            self.robot.step(self.dt)

        while self.robot.step(self.dt) != -1:
            x, y = self.get_pos()
            tx, ty = self.waypoints[self.wp_idx]

            dx, dy = tx - x, ty - y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < ARRIVE_THRESHOLD:
                self.wp_idx = (self.wp_idx + 1) % len(self.waypoints)
                continue

            # 목표 방향 계산
            target_angle = math.atan2(dx, dy)
            heading = self.get_heading()
            angle_diff = target_angle - heading

            # 각도 정규화 [-pi, pi]
            while angle_diff > math.pi: angle_diff -= 2 * math.pi
            while angle_diff < -math.pi: angle_diff += 2 * math.pi

            # P제어 조향
            speed = self.max_speed
            turn = angle_diff * 2.0

            # 큰 각도차 → 제자리 회전
            if abs(angle_diff) > 0.5:
                speed *= 0.3

            left_v = (speed - turn * self.axle_length / 2) / self.wheel_radius
            right_v = (speed + turn * self.axle_length / 2) / self.wheel_radius

            # 속도 제한
            max_v = self.max_speed * 3 / self.wheel_radius
            left_v = max(-max_v, min(max_v, left_v))
            right_v = max(-max_v, min(max_v, right_v))

            self.left_motor.setVelocity(left_v)
            self.right_motor.setVelocity(right_v)


if __name__ == '__main__':
    PatrolController().run()
