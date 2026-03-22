"""
자율주행 수거 로봇 컨트롤러
- A* 경로탐색 (웹 시뮬레이션과 동일한 60×40 그리드)
- GPS + Compass 기반 웨이포인트 추종
- 초음파 센서 장애물 회피
- 4대 로봇 자동 빈 배정 + 순서 최적화
- 배터리 시뮬레이션 (0.15%/m, <15% 긴급 복귀)
- 방향키로 수동 오버라이드 가능
"""
import math
import heapq
from enum import Enum
from controller import Robot, Keyboard

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRID_W, GRID_H = 60, 40
CP = (15, 20)  # 집하장 (그리드 좌표)
NUM_ROBOTS = 4
WHEEL_RADIUS = 0.04
MAX_VEL = 0.5        # m/s
MAX_STEER = 0.45     # rad
KP_STEER = 2.5       # 비례 조향 게인
WAYPOINT_REACH = 1.0  # 웨이포인트 도착 판정 (m)
COLLECT_SEC = 3.0     # 수거 대기 시간 (초)
BATTERY_DRAIN = 0.15  # %/m (웹의 0.3%/cell ÷ 2m/cell)
BATTERY_LOW = 15.0    # 긴급 복귀 임계값
US_EMERGENCY = 0.4    # 긴급 정지 거리 (m)
US_CAUTION = 1.0      # 감속 거리 (m)

# 16개 쓰레기통 (그리드 좌표, 이름)
BIN_POSITIONS = [
    (7, 8, "101-01"), (13, 8, "101-02"),
    (22, 8, "102-01"), (28, 8, "102-02"),
    (7, 20, "103-01"), (13, 20, "103-02"),
    (22, 20, "104-01"), (28, 20, "104-02"),
    (7, 32, "105-01"), (13, 32, "105-02"),
    (22, 32, "106-01"), (28, 32, "106-02"),
    (40, 15, "park-01"), (45, 15, "park-02"),
    (40, 30, "parking-01"), (50, 30, "parking-02"),
]

US_NAMES = ['us_front_left', 'us_front_right',
            'us_side_left', 'us_side_right', 'us_rear']


class State(Enum):
    IDLE = "대기"
    NAV_TO_BIN = "이동중"
    COLLECTING = "수거중"
    NAV_TO_CP = "복귀중"
    CHARGING = "충전복귀"
    DONE = "완료"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ② 그리드 맵 (mock-data.ts 포팅)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_grid():
    grid = [[0] * GRID_W for _ in range(GRID_H)]

    def bld(x1, y1, x2, y2):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                grid[y][x] = 1

    # 외벽
    for x in range(GRID_W):
        grid[0][x] = 1
        grid[GRID_H - 1][x] = 1
    for y in range(GRID_H):
        grid[y][0] = 1
        grid[y][GRID_W - 1] = 1

    # 아파트 1열
    bld(3, 3, 6, 7);    bld(9, 3, 12, 7)
    bld(3, 10, 6, 14);  bld(9, 10, 12, 14)
    bld(3, 22, 6, 26);  bld(9, 22, 12, 26)
    bld(3, 28, 6, 32);  bld(9, 28, 12, 32)
    # 아파트 2열
    bld(18, 3, 21, 7);  bld(24, 3, 27, 7)
    bld(18, 10, 21, 14); bld(24, 10, 27, 14)
    bld(18, 22, 21, 26); bld(24, 22, 27, 26)
    bld(18, 28, 21, 32); bld(24, 28, 27, 32)
    # 아파트 3열 (105동, 106동)
    bld(3, 34, 6, 38);  bld(9, 34, 12, 38)
    bld(18, 34, 21, 38); bld(24, 34, 27, 38)
    # 부대시설
    bld(38, 10, 42, 13)   # 놀이터
    bld(48, 3, 53, 6)     # 관리사무소
    bld(38, 25, 45, 28)   # 주차장1
    bld(48, 25, 55, 28)   # 주차장2
    bld(33, 1, 34, 2)     # 경비실

    return grid


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ③ A* 경로탐색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def astar(grid, start, goal):
    """4방향 A*, 맨해튼 휴리스틱. 웹 시뮬레이션과 동일."""
    sx, sy = start
    gx, gy = goal
    if sx == gx and sy == gy:
        return [goal]

    dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    open_set = [(abs(gx - sx) + abs(gy - sy), 0, sx, sy)]
    g_score = {(sx, sy): 0}
    came_from = {}
    closed = set()

    while open_set:
        _, g, cx, cy = heapq.heappop(open_set)
        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))

        if cx == gx and cy == gy:
            path = []
            cur = (gx, gy)
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append(start)
            path.reverse()
            return path

        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < GRID_W and 0 <= ny < GRID_H and grid[ny][nx] == 0:
                ng = g + 1
                if ng < g_score.get((nx, ny), float('inf')):
                    g_score[(nx, ny)] = ng
                    came_from[(nx, ny)] = (cx, cy)
                    heapq.heappush(open_set, (ng + abs(gx - nx) + abs(gy - ny), ng, nx, ny))

    return []  # 경로 없음


def simplify_path(path):
    """방향 변경점만 유지 → 웨이포인트 수 축소."""
    if len(path) <= 2:
        return list(path)
    result = [path[0]]
    for i in range(1, len(path) - 1):
        pdx = path[i][0] - path[i - 1][0]
        pdy = path[i][1] - path[i - 1][1]
        ndx = path[i + 1][0] - path[i][0]
        ndy = path[i + 1][1] - path[i][1]
        if (pdx, pdy) != (ndx, ndy):
            result.append(path[i])
    result.append(path[-1])
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ④ 좌표 변환
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def grid_to_world(gx, gy):
    return gx * 2.0 - 60.0, 40.0 - gy * 2.0


def world_to_grid(wx, wy):
    gx = int(round((wx + 60.0) / 2.0))
    gy = int(round((40.0 - wy) / 2.0))
    return max(0, min(GRID_W - 1, gx)), max(0, min(GRID_H - 1, gy))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⑤ 미션 플래너 (웹과 동일 알고리즘)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def assign_bins(robot_idx):
    """거리순 정렬 → round-robin → nearest-neighbor 재정렬."""
    sorted_bins = sorted(BIN_POSITIONS, key=lambda b: manhattan((b[0], b[1]), CP))
    my_bins = [sorted_bins[i] for i in range(len(sorted_bins)) if i % NUM_ROBOTS == robot_idx]

    if len(my_bins) <= 1:
        return my_bins

    ordered = []
    remaining = list(my_bins)
    cx, cy = CP
    while remaining:
        best = min(range(len(remaining)),
                   key=lambda i: manhattan((remaining[i][0], remaining[i][1]), (cx, cy)))
        pick = remaining.pop(best)
        ordered.append(pick)
        cx, cy = pick[0], pick[1]
    return ordered


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⑥ 컨트롤러 본체
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AutonomousController:

    def __init__(self):
        self.robot = Robot()
        self.dt = int(self.robot.getBasicTimeStep())
        self.name = self.robot.getName()

        # 구동 모터 (후륜)
        self.lm = self.robot.getDevice('left_wheel_motor')
        self.rm = self.robot.getDevice('right_wheel_motor')
        self.lm.setPosition(float('inf'))
        self.rm.setPosition(float('inf'))
        self.lm.setVelocity(0)
        self.rm.setVelocity(0)

        # 조향 모터 (전륜)
        self.sfl = self.robot.getDevice('steer_fl')
        self.sfr = self.robot.getDevice('steer_fr')

        # GPS
        self.gps = self.robot.getDevice('gps')
        self.gps.enable(self.dt)

        # Compass
        self.compass = self.robot.getDevice('compass')
        self.compass.enable(self.dt)

        # 초음파 센서
        self.us = {}
        for n in US_NAMES:
            s = self.robot.getDevice(n)
            if s:
                s.enable(self.dt)
                self.us[n] = s

        # 카메라 (활성화만)
        for cn in ['realsense_color', 'webcam_color']:
            c = self.robot.getDevice(cn)
            if c:
                c.enable(self.dt * 4)

        # 키보드
        self.kb = Keyboard()
        self.kb.enable(self.dt)

        # 맵
        self.grid = build_grid()

        # 미션 상태
        self.robot_idx = int(self.name.split('_')[1]) - 1 if '_' in self.name else 0
        self.my_bins = assign_bins(self.robot_idx)
        self.bin_idx = 0
        self.state = State.IDLE
        self.waypoints = []
        self.wp_idx = 0
        self.collect_timer = 0.0
        self.battery = 100.0
        self.last_pos = None

        print(f'[{self.name}] 자율주행 컨트롤러 시작 — {len(self.my_bins)}개 빈 배정')
        for i, b in enumerate(self.my_bins):
            print(f'  #{i + 1}: {b[2]} (grid {b[0]},{b[1]})')

    # ── 센서 읽기 ──

    def get_pos(self):
        v = self.gps.getValues()
        return v[0], v[1]

    def get_heading(self):
        v = self.compass.getValues()
        return math.atan2(v[0], v[1])

    def us_dist(self, name):
        s = self.us.get(name)
        if not s:
            return 999.0
        return s.getValue()

    # ── 경로 계산 ──

    def plan_path(self, start_grid, goal_grid):
        path = astar(self.grid, start_grid, goal_grid)
        if not path:
            print(f'[{self.name}] 경로 없음: {start_grid} → {goal_grid}')
            return []
        simple = simplify_path(path)
        return [grid_to_world(gx, gy) for gx, gy in simple]

    def current_grid(self):
        wx, wy = self.get_pos()
        return world_to_grid(wx, wy)

    # ── 모터 제어 ──

    def stop(self):
        self.lm.setVelocity(0)
        self.rm.setVelocity(0)
        self.sfl.setPosition(0)
        self.sfr.setPosition(0)

    def drive(self, speed, steer):
        steer = max(-MAX_STEER, min(MAX_STEER, steer))
        vel = speed / WHEEL_RADIUS
        self.lm.setVelocity(vel)
        self.rm.setVelocity(vel)
        self.sfl.setPosition(steer)
        self.sfr.setPosition(steer)

    # ── 장애물 회피 ──

    def avoid_obstacles(self, speed, steer):
        fl = self.us_dist('us_front_left')
        fr = self.us_dist('us_front_right')
        sl = self.us_dist('us_side_left')
        sr = self.us_dist('us_side_right')
        front = min(fl, fr)

        if speed > 0:
            if front < US_EMERGENCY:
                speed = 0.0
                steer = -MAX_STEER if fl < fr else MAX_STEER
            elif front < US_CAUTION:
                ratio = (front - US_EMERGENCY) / (US_CAUTION - US_EMERGENCY)
                speed *= max(0.15, ratio)
                if fl < fr:
                    steer -= 0.25
                else:
                    steer += 0.25

        if sl < US_EMERGENCY:
            steer -= 0.3
        if sr < US_EMERGENCY:
            steer += 0.3

        return speed, max(-MAX_STEER, min(MAX_STEER, steer))

    # ── 웨이포인트 추종 ──

    def navigate_step(self):
        """현재 웨이포인트를 향해 1스텝 주행. 도착하면 True."""
        if self.wp_idx >= len(self.waypoints):
            self.stop()
            return True

        tx, ty = self.waypoints[self.wp_idx]
        wx, wy = self.get_pos()
        dx, dy = tx - wx, ty - wy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < WAYPOINT_REACH:
            self.wp_idx += 1
            if self.wp_idx >= len(self.waypoints):
                self.stop()
                return True
            tx, ty = self.waypoints[self.wp_idx]
            dx, dy = tx - wx, ty - wy
            dist = math.sqrt(dx * dx + dy * dy)

        desired = math.atan2(dy, dx)
        current = self.get_heading()
        err = desired - current
        while err > math.pi:
            err -= 2 * math.pi
        while err < -math.pi:
            err += 2 * math.pi

        steer = KP_STEER * err
        alignment = max(0, math.cos(err))
        speed = MAX_VEL * (0.3 + 0.7 * alignment)

        speed, steer = self.avoid_obstacles(speed, steer)
        self.drive(speed, steer)
        return False

    # ── 배터리 ──

    def update_battery(self):
        wx, wy = self.get_pos()
        if self.last_pos is not None:
            d = math.sqrt((wx - self.last_pos[0]) ** 2 + (wy - self.last_pos[1]) ** 2)
            self.battery = max(0, self.battery - d * BATTERY_DRAIN)
        self.last_pos = (wx, wy)

    # ── 키보드 오버라이드 ──

    def check_keyboard(self):
        spd, steer = 0.0, 0.0
        pressed = False
        k = self.kb.getKey()
        while k != -1:
            pressed = True
            if k == Keyboard.UP:
                spd = MAX_VEL
            elif k == Keyboard.DOWN:
                spd = -MAX_VEL
            if k == Keyboard.LEFT:
                steer = MAX_STEER
            elif k == Keyboard.RIGHT:
                steer = -MAX_STEER
            k = self.kb.getKey()
        return (spd, steer) if pressed else None

    # ── 상태 전이 ──

    def start_nav_to_bin(self):
        """현재 빈을 향해 경로 계획 후 NAV_TO_BIN 전환."""
        b = self.my_bins[self.bin_idx]
        self.waypoints = self.plan_path(self.current_grid(), (b[0], b[1]))
        self.wp_idx = 0
        self.state = State.NAV_TO_BIN
        print(f'[{self.name}] → 빈 {b[2]} 이동 (wp {len(self.waypoints)}개)')

    def start_nav_to_cp(self):
        """집하장으로 복귀 경로 계획."""
        self.waypoints = self.plan_path(self.current_grid(), CP)
        self.wp_idx = 0
        self.state = State.NAV_TO_CP
        print(f'[{self.name}] → 집하장 복귀')

    # ── 메인 루프 ──

    def run(self):
        # 첫 빈으로 출발
        if self.my_bins:
            self.start_nav_to_bin()

        while self.robot.step(self.dt) != -1:
            self.update_battery()

            # 키보드 오버라이드
            manual = self.check_keyboard()
            if manual:
                spd, steer = manual
                spd, steer = self.avoid_obstacles(spd, steer)
                self.drive(spd, steer)
                continue

            # ── 상태 머신 ──

            if self.state == State.NAV_TO_BIN:
                # 배터리 부족 → 긴급 복귀
                if self.battery < BATTERY_LOW:
                    self.waypoints = self.plan_path(self.current_grid(), CP)
                    self.wp_idx = 0
                    self.state = State.CHARGING
                    print(f'[{self.name}] 배터리 {self.battery:.1f}% — 긴급 복귀!')
                    continue

                arrived = self.navigate_step()
                if arrived:
                    b = self.my_bins[self.bin_idx]
                    print(f'[{self.name}] 빈 {b[2]} 도착 — 수거 시작')
                    self.state = State.COLLECTING
                    self.collect_timer = 0.0
                    self.stop()

            elif self.state == State.COLLECTING:
                self.collect_timer += self.dt / 1000.0
                if self.collect_timer >= COLLECT_SEC:
                    b = self.my_bins[self.bin_idx]
                    print(f'[{self.name}] 빈 {b[2]} 수거 완료')
                    self.start_nav_to_cp()

            elif self.state == State.NAV_TO_CP:
                arrived = self.navigate_step()
                if arrived:
                    self.bin_idx += 1
                    if self.bin_idx >= len(self.my_bins):
                        print(f'[{self.name}] 모든 빈 수거 완료!')
                        self.state = State.DONE
                        self.stop()
                    else:
                        print(f'[{self.name}] 집하장 도착 — 다음 빈으로')
                        self.start_nav_to_bin()

            elif self.state == State.CHARGING:
                arrived = self.navigate_step()
                if arrived:
                    print(f'[{self.name}] 집하장 도착 — 충전 필요 (배터리 {self.battery:.1f}%)')
                    self.state = State.DONE
                    self.stop()

            elif self.state == State.DONE:
                self.stop()


if __name__ == '__main__':
    AutonomousController().run()
