"""
자율주행 수거 로봇 컨트롤러
- A* 경로탐색 (웹 시뮬레이션과 동일한 200×140 그리드)
- GPS + Compass 기반 웨이포인트 추종
- 초음파 센서 장애물 회피
- 4대 로봇 자동 빈 배정 + 순서 최적화
- 배터리 시뮬레이션 (0.15%/m, <15% 충전소 복귀)
- 방향키로 수동 오버라이드 가능
"""
import math
import heapq
import json
import urllib.request
from enum import Enum
from controller import Robot, Keyboard

BACKEND_URL = "http://localhost:8000/api/webots/state"
SEND_INTERVAL = 0.2  # 상태 전송 간격 (초, 5Hz)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRID_W, GRID_H = 200, 140
CP = (99, 69)  # 집하장 (그리드 좌표)
NUM_ROBOTS = 4
WHEEL_RADIUS = 0.04
MAX_VEL = 0.5        # m/s
MAX_STEER = 0.45     # rad
KP_STEER = 2.5       # 비례 조향 게인
WAYPOINT_REACH = 1.0  # 웨이포인트 도착 판정 (m)
COLLECT_SEC = 3.0     # 수거 대기 시간 (초)
BATTERY_DRAIN = 0.10  # %/m (larger map, longer distances)
BATTERY_LOW = 15.0    # 긴급 복귀 임계값
US_EMERGENCY = 0.4    # 긴급 정지 거리 (m)
US_CAUTION = 1.0      # 감속 거리 (m)
STALL_TIMEOUT = 2.0   # 정지 후 우회 판단까지 대기 시간 (초)
REPLAN_COOLDOWN = 3.0 # 경로 재탐색 쿨다운 (초)

# 24개 쓰레기통 (그리드 좌표, 이름) — 48-building layout
BIN_POSITIONS = [
    # NW Zone
    (17,13,"수거NW01"), (50,11,"수거NW02"), (15,32,"수거NW03"),
    (49,30,"수거NW04"), (17,50,"수거NW05"), (49,50,"수거NW06"),
    # NE Zone
    (118,13,"수거NE01"), (151,11,"수거NE02"), (117,32,"수거NE03"),
    (152,30,"수거NE04"), (118,50,"수거NE05"), (152,49,"수거NE06"),
    # SW Zone
    (17,83,"수거SW01"), (49,83,"수거SW02"), (16,103,"수거SW03"),
    (49,101,"수거SW04"), (17,122,"수거SW05"), (49,121,"수거SW06"),
    # SE Zone
    (117,83,"수거SE01"), (151,82,"수거SE02"), (118,103,"수거SE03"),
    (151,101,"수거SE04"), (118,122,"수거SE05"), (151,121,"수거SE06"),
]

# 충전소 (각 로봇별)
CHARGING_STATIONS = [
    (35, 35),   # Robot_1 (NW)
    (135, 35),  # Robot_2 (NE)
    (35, 105),  # Robot_3 (SW)
    (135, 105),  # Robot_4 (SE)
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

    # NW Row 1 (25F)
    bld(5,3,12,8); bld(22,4,27,11); bld(37,3,46,8); bld(56,5,61,12)
    # NW Row 2 (22F)
    bld(4,22,11,27); bld(20,24,25,31); bld(35,22,44,27); bld(54,23,61,28)
    # NW Row 3 (18F)
    bld(6,42,11,49); bld(22,43,31,48); bld(40,42,47,47); bld(56,44,61,51)
    # NE Row 1 (25F)
    bld(106,3,113,8); bld(123,5,128,12); bld(138,3,147,8); bld(157,4,162,11)
    # NE Row 2 (22F)
    bld(105,22,114,27); bld(124,24,129,31); bld(139,22,146,27); bld(156,23,163,28)
    # NE Row 3 (18F)
    bld(107,42,112,49); bld(122,43,131,48); bld(141,44,148,49); bld(158,42,163,49)
    # SW Row 4 (15F)
    bld(5,75,14,80); bld(24,74,29,81); bld(39,76,46,81); bld(55,74,60,81)
    # SW Row 5 (12F)
    bld(4,93,11,98); bld(22,95,27,102); bld(37,93,46,98); bld(56,94,61,101)
    # SW Row 6 (10F)
    bld(6,113,11,120); bld(21,114,30,119); bld(40,113,47,118); bld(56,115,61,122)
    # SE Row 4 (15F)
    bld(106,74,111,81); bld(121,76,128,81); bld(138,74,147,79); bld(157,75,162,82)
    # SE Row 5 (12F)
    bld(105,93,114,98); bld(124,95,129,102); bld(139,93,146,98); bld(156,94,163,99)
    # SE Row 6 (10F)
    bld(107,113,112,120); bld(122,114,131,119); bld(141,115,148,120); bld(158,113,163,120)
    # Facilities
    bld(70,55,81,63)     # 주차장A
    bld(14,125,27,133)   # 주차장B
    bld(170,125,183,133) # 주차장C
    bld(68,34,77,41)     # 놀이터1
    bld(170,34,179,41)   # 놀이터2
    bld(170,55,181,62)   # 관리사무소
    bld(95,1,104,3)      # 경비실N
    bld(95,136,104,138)  # 경비실S

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
    return gx * 2.0 - 200.0, 140.0 - gy * 2.0


def world_to_grid(wx, wy):
    gx = int(round((wx + 200.0) / 2.0))
    gy = int(round((140.0 - wy) / 2.0))
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
        self.last_send_time = 0.0   # 마지막 상태 전송 시각

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

    # ── 웹 실시간 전송 ──

    def send_state(self):
        """현재 로봇 상태를 백엔드로 HTTP POST (실패 시 무시)."""
        if self.sim_time - self.last_send_time < SEND_INTERVAL:
            return
        self.last_send_time = self.sim_time
        gx, gy = self.current_grid()
        payload = json.dumps({
            "robot_id": self.robot_idx + 1,
            "name": self.name,
            "x": gx, "y": gy,
            "battery": round(self.battery, 1),
            "state": self.state.value,
            "bin_name": self.my_bins[self.bin_idx][2] if self.bin_idx < len(self.my_bins) else None,
            "bin_idx": self.bin_idx,
            "bin_total": len(self.my_bins),
        }).encode()
        try:
            req = urllib.request.Request(
                BACKEND_URL, data=payload,
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=0.15)
        except Exception:
            pass  # 백엔드 미실행 시 무시

    # ── 메인 루프 ──

    def run(self):
        # 첫 빈으로 출발
        if self.my_bins:
            self.start_nav_to_bin()

        while self.robot.step(self.dt) != -1:
            self.sim_time += self.dt / 1000.0
            self.update_battery()
            self.send_state()

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
