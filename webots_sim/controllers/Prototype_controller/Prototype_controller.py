"""시제품 테스트용 Webots 컨트롤러.

- 30×20 소형 테스트 랩 (웹 시제품 시뮬레이션과 동일 맵)
- 로봇 2대, 쓰레기통 4개
- A* 경로탐색 + 초음파 장애물 회피
- 배터리: 2S LiPo 7.4V 2200mAh 기준
- 웹 /simulation-prototype 페이지와 실시간 동기화

백엔드 엔드포인트:
  POST /api/webots-prototype/state  (200ms 마다 상태 전송)
  WS   /ws/webots-prototype         (웹 클라이언트 수신)
"""
import math
import heapq
import json
import os
import urllib.request
from enum import Enum
from controller import Robot, Keyboard

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/webots-prototype/state")
SEND_INTERVAL = 0.2  # 5Hz

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시제품 스펙 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GRID_W, GRID_H = 40, 30              # 웹 시뮬레이션과 동일
CELL_M = 0.5                          # 1셀 = 0.5m
CP = (20, 27)                         # 수거함 (그리드 좌표)
NUM_ROBOTS = 2

# NP01D-288 (6V DC 모터) 기준 실제 속도
MAX_VEL = 0.3        # m/s (시제품 속도, 기존 1.5에서 축소)
MAX_STEER = 0.45     # rad (MG996R 서보)
KP_STEER = 2.5
WAYPOINT_REACH = 0.3  # m

COLLECT_SEC = 3.0
# 2S LiPo 2200mAh 기준 배터리 소모율
# 평균 2A 소비 가정, 사용 가능 1760mAh → 약 53분 런타임
# 테스트 공간(~15m 이동) 기준 역산: 0.1%/m
BATTERY_DRAIN = 0.1
BATTERY_LOW = 15.0

US_EMERGENCY = 0.15   # 15cm (소형 로봇이라 축소)
US_CAUTION = 0.35     # 35cm
STALL_TIMEOUT = 2.0
REPLAN_COOLDOWN = 3.0

# 쓰레기통 4개 (웹 시제품 시뮬레이션과 동일 좌표)
BIN_POSITIONS = [
    (10, 8, "BIN-01"),
    (29, 8, "BIN-02"),
    (10, 21, "BIN-03"),
    (29, 21, "BIN-04"),
]

# 충전소 (로봇당 1개)
CHARGING_STATIONS = [
    (2, 27),   # 로봇-A
    (37, 27),  # 로봇-B
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
# 30×20 테스트 랩 그리드 (웹과 동일)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_grid():
    grid = [[0] * GRID_W for _ in range(GRID_H)]

    def wall(x1, y1, x2, y2):
        for y in range(y1, min(y2 + 1, GRID_H)):
            for x in range(x1, min(x2 + 1, GRID_W)):
                grid[y][x] = 1

    # 외벽
    for x in range(GRID_W):
        grid[0][x] = 1
        grid[GRID_H - 1][x] = 1
    for y in range(GRID_H):
        grid[y][0] = 1
        grid[y][GRID_W - 1] = 1

    # 건물 4동 (소형)
    wall(4, 3, 8, 6)      # 101동
    wall(14, 3, 18, 6)    # 102동
    wall(4, 16, 8, 19)    # 103동
    wall(14, 16, 18, 19)  # 104동
    # 놀이터
    wall(31, 12, 34, 14)
    # 주차장
    wall(23, 24, 26, 25)
    # 경비실
    wall(19, 28, 20, 28)

    return grid


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A* 경로탐색 (4방향, 맨해튼)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def astar(grid, start, goal):
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

    return []


def simplify_path(path):
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
# 좌표 변환 (그리드 ↔ Webots 월드)
# 월드 원점은 맵 중앙
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def grid_to_world(gx, gy):
    """그리드 셀 중심 → Webots 월드 좌표 (m).
    그리드 중심 (20, 15) = 월드 원점 (0, 0).
    wx = (gx - 20) * 0.5
    wy = (15 - gy) * 0.5  (Y축 반전)
    """
    wx = (gx - GRID_W / 2) * CELL_M
    wy = (GRID_H / 2 - gy) * CELL_M
    return wx, wy


def world_to_grid(wx, wy):
    gx = int(wx / CELL_M + GRID_W / 2)
    gy = int(GRID_H / 2 - wy / CELL_M)
    return max(0, min(GRID_W - 1, gx)), max(0, min(GRID_H - 1, gy))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 빈 배정 (최근접 이웃)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def assign_bins(num_robots=NUM_ROBOTS):
    """로봇별 쓰레기통 할당. 2대가 4개를 나눠 수거."""
    assignments = [[] for _ in range(num_robots)]
    remaining = list(BIN_POSITIONS)
    robot_positions = [CHARGING_STATIONS[i] for i in range(num_robots)]

    while remaining:
        for rid in range(num_robots):
            if not remaining:
                break
            last = assignments[rid][-1] if assignments[rid] else robot_positions[rid]
            nearest_idx = min(
                range(len(remaining)),
                key=lambda i: abs(remaining[i][0] - last[0]) + abs(remaining[i][1] - last[1])
            )
            assignments[rid].append(remaining.pop(nearest_idx))
    return assignments


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTTP 전송 (백엔드로 상태 POST)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def send_state(data):
    try:
        req = urllib.request.Request(
            BACKEND_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        urllib.request.urlopen(req, timeout=0.5)
    except Exception as e:
        pass  # 백엔드 꺼져있어도 시뮬레이션 계속


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 로봇 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PrototypeRobot:
    def __init__(self, robot_id, name, color):
        self.id = robot_id
        self.name = name
        self.color = color
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # 디바이스 초기화
        self._init_devices()

        # 상태
        self.state = State.IDLE
        self.battery = 100.0
        self.grid = build_grid()
        self.assigned_bins = []
        self.current_bin_idx = 0
        self.collected = []
        self.path = []
        self.path_idx = 0
        self.distance_traveled = 0.0
        self.last_pos = None
        self.stall_timer = 0
        self.last_replan = 0
        self.collect_timer = 0
        self.phase = "to_bin"   # to_bin | to_cp | charging | done
        self.last_send = 0

        cs = CHARGING_STATIONS[robot_id - 1]
        self.cs_grid = cs
        self.start_position = grid_to_world(*cs)

    def _init_devices(self):
        """모터/센서 초기화. 실제 Webots 디바이스 이름은 proto 파일에 맞게 조정 필요."""
        try:
            self.left_motor = self.robot.getDevice('left_wheel_motor')
            self.right_motor = self.robot.getDevice('right_wheel_motor')
            for m in [self.left_motor, self.right_motor]:
                m.setPosition(float('inf'))
                m.setVelocity(0)
        except Exception:
            self.left_motor = None
            self.right_motor = None

        try:
            self.gps = self.robot.getDevice('gps')
            self.gps.enable(self.timestep)
            self.compass = self.robot.getDevice('compass')
            self.compass.enable(self.timestep)
        except Exception:
            self.gps = None
            self.compass = None

        self.ultrasonics = []
        for name in US_NAMES:
            try:
                s = self.robot.getDevice(name)
                s.enable(self.timestep)
                self.ultrasonics.append(s)
            except Exception:
                self.ultrasonics.append(None)

    def get_position(self):
        if self.gps:
            p = self.gps.getValues()
            if math.isnan(p[0]) or math.isnan(p[1]):
                return self.start_position
            return p[0], p[1]
        return self.start_position

    def get_heading(self):
        if self.compass:
            c = self.compass.getValues()
            return math.atan2(c[0], c[2])
        return 0.0

    def start_mission(self):
        """쓰레기통 할당받아 미션 시작."""
        all_assignments = assign_bins()
        self.assigned_bins = all_assignments[self.id - 1]
        if self.assigned_bins:
            self.state = State.NAV_TO_BIN
            self.phase = "to_bin"
            self._plan_to_current_bin()

    def _plan_to_current_bin(self):
        if self.current_bin_idx >= len(self.assigned_bins):
            self._plan_to_cp()
            return
        bx, by, _ = self.assigned_bins[self.current_bin_idx]
        cur_wx, cur_wy = self.get_position()
        cur_gx, cur_gy = world_to_grid(cur_wx, cur_wy)
        path = astar(self.grid, (cur_gx, cur_gy), (bx, by))
        self.path = simplify_path(path) if path else []
        self.path_idx = 0

    def _plan_to_cp(self):
        cur_wx, cur_wy = self.get_position()
        cur_gx, cur_gy = world_to_grid(cur_wx, cur_wy)
        path = astar(self.grid, (cur_gx, cur_gy), CP)
        self.path = simplify_path(path) if path else []
        self.path_idx = 0
        self.state = State.NAV_TO_CP
        self.phase = "to_cp"

    def _plan_to_cs(self):
        cur_wx, cur_wy = self.get_position()
        cur_gx, cur_gy = world_to_grid(cur_wx, cur_wy)
        path = astar(self.grid, (cur_gx, cur_gy), self.cs_grid)
        self.path = simplify_path(path) if path else []
        self.path_idx = 0
        self.state = State.CHARGING
        self.phase = "charging"

    def step(self):
        """매 타임스텝 실행. Webots robot.step() 후 호출."""
        # 배터리 체크
        if self.battery <= BATTERY_LOW and self.phase not in ("charging", "done"):
            self._plan_to_cs()

        # 경로 이동
        if self.path_idx < len(self.path):
            target = self.path[self.path_idx]
            tx, ty = grid_to_world(*target)
            cur_wx, cur_wy = self.get_position()
            dx = tx - cur_wx
            dy = ty - cur_wy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < WAYPOINT_REACH:
                self.path_idx += 1
                if self.path_idx >= len(self.path):
                    self._on_path_complete()
            else:
                self._drive_toward(tx, ty)

        # 배터리 소모
        cur_pos = self.get_position()
        if self.last_pos and not (math.isnan(cur_pos[0]) or math.isnan(cur_pos[1])):
            d = math.sqrt((cur_pos[0] - self.last_pos[0]) ** 2 + (cur_pos[1] - self.last_pos[1]) ** 2)
            self.distance_traveled += d
            self.battery = max(0, self.battery - d * BATTERY_DRAIN)
        self.last_pos = cur_pos

    def _drive_toward(self, tx, ty):
        """단순 P 제어기 (서보 조향 + DC 모터)."""
        cur_wx, cur_wy = self.get_position()
        heading = self.get_heading()
        target_heading = math.atan2(ty - cur_wy, tx - cur_wx)
        err = target_heading - heading
        while err > math.pi: err -= 2 * math.pi
        while err < -math.pi: err += 2 * math.pi

        # 초음파 장애물 회피
        min_us = self._min_ultrasonic()
        if min_us < US_EMERGENCY:
            self._set_wheel_vel(0, 0)
            return
        speed_factor = 1.0 if min_us > US_CAUTION else min_us / US_CAUTION
        speed = MAX_VEL * speed_factor * math.cos(err)

        # 차동 구동 근사 (L298N + NP01D-288)
        steer = max(-MAX_STEER, min(MAX_STEER, KP_STEER * err))
        v_left = speed - steer * MAX_VEL * 0.5
        v_right = speed + steer * MAX_VEL * 0.5
        self._set_wheel_vel(v_left, v_right)

    def _set_wheel_vel(self, vl, vr):
        if self.left_motor and self.right_motor:
            wheel_radius = 0.04
            self.left_motor.setVelocity(vl / wheel_radius)
            self.right_motor.setVelocity(vr / wheel_radius)

    def _min_ultrasonic(self):
        vals = [s.getValue() for s in self.ultrasonics if s]
        return min(vals) if vals else 10.0

    def _on_path_complete(self):
        if self.phase == "to_bin":
            bin_code = self.assigned_bins[self.current_bin_idx][2]
            self.collected.append(bin_code)
            self.current_bin_idx += 1
            self.state = State.COLLECTING
            self.collect_timer = COLLECT_SEC
        elif self.phase == "to_cp":
            self.state = State.DONE
            self.phase = "done"
        elif self.phase == "charging":
            self.state = State.IDLE  # 충전 중

    def update(self):
        """매 시뮬레이션 스텝. 수거 대기 처리 + 상태 전송."""
        dt = self.timestep / 1000.0

        # 수거 중 대기
        if self.state == State.COLLECTING:
            self.collect_timer -= dt
            self._set_wheel_vel(0, 0)
            if self.collect_timer <= 0:
                if self.current_bin_idx < len(self.assigned_bins):
                    self.state = State.NAV_TO_BIN
                    self.phase = "to_bin"
                    self._plan_to_current_bin()
                else:
                    self._plan_to_cp()

        # 충전 중
        if self.phase == "charging" and self.state == State.IDLE:
            self.battery = min(100, self.battery + 5 * dt)

        # 일반 이동
        if self.state in (State.NAV_TO_BIN, State.NAV_TO_CP, State.CHARGING):
            self.step()

        # 백엔드로 상태 전송
        self.last_send += dt
        if self.last_send >= SEND_INTERVAL:
            self.last_send = 0
            self._send_state()

    def _send_state(self):
        cur_wx, cur_wy = self.get_position()
        cur_gx, cur_gy = world_to_grid(cur_wx, cur_wy)
        current_bin = None
        if self.phase == "to_bin" and self.current_bin_idx < len(self.assigned_bins):
            current_bin = self.assigned_bins[self.current_bin_idx][2]
        send_state({
            "robot_id": self.id,
            "name": self.name,
            "color": self.color,
            "x": cur_gx,
            "y": cur_gy,
            "world_x": cur_wx,
            "world_y": cur_wy,
            "battery": round(self.battery, 1),
            "state": self.state.value,
            "phase": self.phase,
            "assigned_bins": [b[2] for b in self.assigned_bins],
            "collected_bins": self.collected,
            "current_bin": current_bin,
            "distance": round(self.distance_traveled, 2),
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webots 컨트롤러는 로봇 1대씩 실행되므로 환경변수로 ID 지정
# 혹은 로봇 이름에서 파싱
def main():
    # 로봇 이름은 Webots에서 Robot 노드의 name 필드로 결정됨
    # Robot() 생성 후 getName()으로 확인
    temp_robot = Robot()
    timestep = int(temp_robot.getBasicTimeStep())
    robot_name = temp_robot.getName()
    print(f"[Prototype] 로봇 이름: {robot_name}")

    if "A" in robot_name or robot_name.endswith("1"):
        robot_id, name, color = 1, "로봇-A", "#ef4444"
    else:
        robot_id, name, color = 2, "로봇-B", "#3b82f6"

    # GPS/센서 초기화 대기 (첫 몇 스텝은 NaN 반환)
    print(f"[{name}] 센서 초기화 대기 중...")
    for _ in range(10):
        if temp_robot.step(timestep) == -1:
            return

    # PrototypeRobot은 내부에서 Robot()을 또 생성하므로
    # 대신 temp_robot을 직접 사용하도록 수정
    bot = PrototypeRobot.__new__(PrototypeRobot)
    bot.id = robot_id
    bot.name = name
    bot.color = color
    bot.robot = temp_robot
    bot.timestep = timestep
    bot._init_devices()

    bot.state = State.IDLE
    bot.battery = 100.0
    bot.grid = build_grid()
    bot.assigned_bins = []
    bot.current_bin_idx = 0
    bot.collected = []
    bot.path = []
    bot.path_idx = 0
    bot.distance_traveled = 0.0
    bot.last_pos = None
    bot.stall_timer = 0
    bot.last_replan = 0
    bot.collect_timer = 0
    bot.phase = "to_bin"
    bot.last_send = 0

    cs = CHARGING_STATIONS[robot_id - 1]
    bot.cs_grid = cs
    bot.start_position = grid_to_world(*cs)

    # GPS 값 확인
    pos = bot.get_position()
    print(f"[{name}] GPS 위치: {pos}")

    # 미션 시작
    bot.start_mission()
    print(f"[{name}] 미션 시작 — 쓰레기통 {len(bot.assigned_bins)}개 할당")

    while bot.robot.step(bot.timestep) != -1:
        bot.update()


if __name__ == "__main__":
    main()
