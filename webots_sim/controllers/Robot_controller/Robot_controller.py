"""
자율주행 수거 로봇 컨트롤러
- A* 경로탐색 (웹 시뮬레이션과 동일한 120×80 그리드)
- GPS + Compass 기반 웨이포인트 추종
- 초음파 센서 장애물 회피
- 4대 로봇 자동 빈 배정 + 순서 최적화
- 배터리 시뮬레이션 (0.15%/m, <15% 충전소 복귀)
- 방향키로 수동 오버라이드 가능
"""
import math
import heapq
from enum import Enum
from controller import Robot, Keyboard

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRID_W, GRID_H = 120, 80
CP = (59, 39)  # 집하장 (그리드 좌표)
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
STALL_TIMEOUT = 2.0   # 정지 후 우회 판단까지 대기 시간 (초)
REPLAN_COOLDOWN = 3.0 # 경로 재탐색 쿨다운 (초)

# 40개 쓰레기통 (그리드 좌표, 이름) — mock-data.ts 매칭
BIN_POSITIONS = [
    # NW (101~108동) — staggered layout
    (8,9,"101"), (21,12,"102"), (35,8,"103"), (48,13,"104"),
    (7,23,"105"), (19,27,"106"), (33,21,"107"), (46,23,"108"),
    # NE (109~114동)
    (69,9,"109"), (83,13,"110"), (98,8,"111"), (111,12,"112"),
    (70,24,"113"), (85,24,"114"),
    # SW (115~120동)
    (8,52,"115"), (22,49,"116"), (36,53,"117"), (48,50,"118"),
    (8,65,"119"), (22,65,"120"),
    # SE (121~126동)
    (69,51,"121"), (83,51,"122"), (97,52,"123"), (110,52,"124"),
    (69,67,"125"), (84,64,"126"),
    # Facilities
    (16,34,"주차A-1"), (20,34,"주차A-2"),
    (37,57,"주차B-1"), (41,57,"주차B-2"),
    (97,57,"주차C-1"), (102,57,"주차C-2"),
    (38,27,"놀이터1"), (91,27,"놀이터2"),
    (99,23,"관리-1"), (103,23,"관리-2"),
    (55,36,"광장-1"), (64,36,"광장-2"),
    (55,43,"광장-3"), (64,43,"광장-4"),
]

# 충전소 (각 로봇별)
CHARGING_STATIONS = [
    (25, 13),   # Robot_1 (NW)
    (90, 13),   # Robot_2 (NE)
    (25, 55),   # Robot_3 (SW)
    (90, 55),   # Robot_4 (SE)
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

    # NW — staggered, mixed orientations
    bld(4,3,11,8)     # 101
    bld(18,4,23,11)   # 102
    bld(30,2,39,7)    # 103
    bld(45,5,50,12)   # 104
    bld(3,17,10,22)   # 105
    bld(16,19,21,26)  # 106
    bld(28,15,37,20)  # 107
    bld(42,17,49,22)  # 108
    # NE
    bld(65,3,72,8)    # 109
    bld(80,5,85,12)   # 110
    bld(93,2,102,7)   # 111
    bld(108,4,113,11) # 112
    bld(66,18,73,23)  # 113
    bld(82,16,87,23)  # 114
    # SW
    bld(5,44,10,51)   # 115
    bld(17,43,26,48)  # 116
    bld(33,45,38,52)  # 117
    bld(44,44,51,49)  # 118
    bld(4,59,11,64)   # 119
    bld(19,57,24,64)  # 120
    # SE
    bld(64,45,73,50)  # 121
    bld(80,43,85,50)  # 122
    bld(94,44,99,51)  # 123
    bld(106,46,113,51)# 124
    bld(66,59,71,66)  # 125
    bld(79,58,88,63)  # 126
    # Facilities
    bld(13,28,22,33)  # 주차장A
    bld(33,58,44,63)  # 주차장B
    bld(94,58,105,63) # 주차장C
    bld(34,28,41,33)  # 놀이터1
    bld(87,28,94,33)  # 놀이터2
    bld(96,17,105,22) # 관리사무소
    bld(56,1,63,3)    # 경비실N
    bld(56,76,63,78)  # 경비실S

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
    return gx * 2.0 - 120.0, 80.0 - gy * 2.0


def world_to_grid(wx, wy):
    gx = int(round((wx + 120.0) / 2.0))
    gy = int(round((80.0 - wy) / 2.0))
    return max(0, min(GRID_W - 1, gx)), max(0, min(GRID_H - 1, gy))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⑤ 미션 플래너 (존 기반 배정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def assign_bins(robot_idx):
    """존 기반 배정: 각 빈을 가장 가까운 충전소에 할당, nearest-neighbor 순서."""
    cs = CHARGING_STATIONS[robot_idx]
    all_bins = [(gx, gy, name) for gx, gy, name in BIN_POSITIONS]

    # Step 1: 각 빈을 가장 가까운 충전소에 할당
    assignments = [[] for _ in range(NUM_ROBOTS)]
    for b in all_bins:
        dists = [abs(b[0] - s[0]) + abs(b[1] - s[1]) for s in CHARGING_STATIONS]
        nearest = dists.index(min(dists))
        assignments[nearest].append(b)

    # Step 2: nearest-neighbor 순서로 정렬
    my_bins = assignments[robot_idx]
    if not my_bins:
        return []

    ordered = []
    cx, cy = cs
    remaining = list(my_bins)
    while remaining:
        remaining.sort(key=lambda b: abs(b[0] - cx) + abs(b[1] - cy))
        nxt = remaining.pop(0)
        ordered.append(nxt)
        cx, cy = nxt[0], nxt[1]
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
        cs = CHARGING_STATIONS[self.robot_idx]
        self.home = cs  # 충전소 (CP 대신)
        self.my_bins = assign_bins(self.robot_idx)
        self.bin_idx = 0
        self.state = State.IDLE
        self.waypoints = []
        self.wp_idx = 0
        self.collect_timer = 0.0
        self.battery = 100.0
        self.last_pos = None
        # Smart obstacle handling
        self.stall_time = 0.0       # 정지 누적 시간
        self.last_progress_pos = None  # 마지막 진행된 위치
        self.last_replan_time = 0.0 # 마지막 재탐색 시각
        self.sim_time = 0.0         # 시뮬레이션 시간

        print(f'[{self.name}] 자율주행 컨트롤러 시작 — {len(self.my_bins)}개 빈 배정 (충전소: {cs})')
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
        """초음파 기반 반응형 회피 + 정체 감지 → 경로 재탐색."""
        fl = self.us_dist('us_front_left')
        fr = self.us_dist('us_front_right')
        sl = self.us_dist('us_side_left')
        sr = self.us_dist('us_side_right')
        rear = self.us_dist('us_rear')
        front = min(fl, fr)
        dt = self.dt / 1000.0  # timestep in seconds

        is_blocked = False
        if speed > 0:
            if front < US_EMERGENCY:
                # Phase 1: 긴급 정지 — 1~2초 대기
                speed = 0.0
                is_blocked = True
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

        steer = max(-MAX_STEER, min(MAX_STEER, steer))

        # ── 정체 감지 및 스마트 회피 ──
        if is_blocked:
            self.stall_time += dt
            if self.stall_time >= STALL_TIMEOUT:
                # Phase 2: 대기 후 우회 시도
                if self.sim_time - self.last_replan_time > REPLAN_COOLDOWN:
                    # 후진 1초 → 측면 회전 → 경로 재탐색
                    if self.stall_time < STALL_TIMEOUT + 1.0:
                        # 후진
                        speed = -0.3
                        steer = 0.0
                    elif self.stall_time < STALL_TIMEOUT + 2.0:
                        # 측면 회전 (좌우 중 빈 쪽으로)
                        speed = 0.15
                        if fl < fr:
                            steer = -MAX_STEER  # 우회전 (왼쪽에 장애물)
                        else:
                            steer = MAX_STEER   # 좌회전 (오른쪽에 장애물)
                    else:
                        # 재탐색
                        self.stall_time = 0.0
                        self.last_replan_time = self.sim_time
                        self._replan_path()
                        speed = 0.0
        else:
            # 진행 중이면 정체 타이머 리셋
            if self.stall_time > 0:
                self.stall_time = max(0, self.stall_time - dt * 2)  # 점진적 리셋

        return speed, steer

    def _replan_path(self):
        """현재 위치에서 목표까지 경로 재탐색."""
        if not self.waypoints or self.state == State.DONE:
            return
        # 현재 목표 결정
        if self.state == State.NAV_TO_BIN and self.bin_idx < len(self.my_bins):
            b = self.my_bins[self.bin_idx]
            goal = (b[0], b[1])
        elif self.state in (State.NAV_TO_CP, State.CHARGING):
            goal = self.home
        else:
            return
        cur = self.current_grid()
        new_wps = self.plan_path(cur, goal)
        if new_wps and len(new_wps) > 1:
            self.waypoints = new_wps
            self.wp_idx = 0
            print(f'[{self.name}] 경로 재탐색 ({len(new_wps)} 웨이포인트)')

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
        """집하장(충전소)으로 복귀 경로 계획."""
        self.waypoints = self.plan_path(self.current_grid(), self.home)
        self.wp_idx = 0
        self.state = State.NAV_TO_CP
        print(f'[{self.name}] → 충전소 복귀')

    # ── 메인 루프 ──

    def run(self):
        # 첫 빈으로 출발
        if self.my_bins:
            self.start_nav_to_bin()

        while self.robot.step(self.dt) != -1:
            self.sim_time += self.dt / 1000.0
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
                # 배터리 부족 → 충전소 복귀
                if self.battery < BATTERY_LOW:
                    self.waypoints = self.plan_path(self.current_grid(), self.home)
                    self.wp_idx = 0
                    self.state = State.CHARGING
                    print(f'[{self.name}] 배터리 부족! 충전소로 복귀 (배터리 {self.battery:.1f}%)')
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
                        print(f'[{self.name}] 충전소 도착 — 다음 빈으로')
                        self.start_nav_to_bin()

            elif self.state == State.CHARGING:
                arrived = self.navigate_step()
                if arrived:
                    print(f'[{self.name}] 충전소 도착 — 충전 필요 (배터리 {self.battery:.1f}%)')
                    self.state = State.DONE
                    self.stop()

            elif self.state == State.DONE:
                self.stop()


if __name__ == '__main__':
    AutonomousController().run()
