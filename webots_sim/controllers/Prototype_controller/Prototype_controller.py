"""시제품 테스트용 Webots 컨트롤러 (v2).

- 40×30 소형 아파트 단지 (웹 시뮬레이션과 동일 맵)
- 로봇 2대, 쓰레기통 4개
- A* 경로탐색 + 초음파 회피 + 스톨 복구
- 웹 /simulation-prototype 과 실시간 동기화

POST /api/webots-prototype/state (200ms)
"""
import math
import heapq
import json
import os
import urllib.request
from enum import Enum
from controller import Robot

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/webots-prototype/state")
SEND_INTERVAL = 0.2

# ━━ 그리드/물리 상수 ━━
GRID_W, GRID_H = 40, 30
CELL_M = 0.5
CP = (20, 27)
NUM_ROBOTS = 2

MAX_VEL = 1.0
MAX_STEER = 0.6
KP_STEER = 3.0
WAYPOINT_REACH = 0.6    # 넓게 → 웨이포인트 쉽게 통과

COLLECT_SEC = 2.0
BATTERY_DRAIN = 0.1
BATTERY_LOW = 15.0

# 초음파 — 벽에 막히면 후진/회전으로 탈출
US_STOP = 0.15
US_SLOW = 0.4

# 스톨 감지
STALL_DIST = 0.05       # 이만큼도 안 움직였으면 스톨
STALL_TIME = 1.5        # 초
REVERSE_TIME = 0.8      # 후진 시간
TURN_TIME = 0.6         # 회전 시간
REPLAN_COOLDOWN = 2.0

BIN_POSITIONS = [
    (10, 8, "BIN-01"),
    (29, 8, "BIN-02"),
    (10, 21, "BIN-03"),
    (29, 21, "BIN-04"),
]

CHARGING_STATIONS = [
    (2, 27),
    (37, 27),
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


class Recovery(Enum):
    NONE = 0
    REVERSE = 1
    TURN = 2


# ━━ 그리드 ━━
def build_grid():
    grid = [[0] * GRID_W for _ in range(GRID_H)]

    def w(x1, y1, x2, y2):
        for y in range(y1, min(y2 + 1, GRID_H)):
            for x in range(x1, min(x2 + 1, GRID_W)):
                grid[y][x] = 1

    for x in range(GRID_W):
        grid[0][x] = 1; grid[GRID_H - 1][x] = 1
    for y in range(GRID_H):
        grid[y][0] = 1; grid[y][GRID_W - 1] = 1

    w(4, 3, 8, 6)
    w(14, 3, 18, 6)
    w(4, 16, 8, 19)
    w(14, 16, 18, 19)
    w(31, 12, 34, 14)
    w(23, 24, 26, 25)
    w(19, 28, 20, 28)
    return grid


# ━━ A* ━━
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


# ━━ 좌표 변환 ━━
def grid_to_world(gx, gy):
    return (gx - GRID_W / 2) * CELL_M, (GRID_H / 2 - gy) * CELL_M


def world_to_grid(wx, wy):
    gx = int(round(wx / CELL_M + GRID_W / 2))
    gy = int(round(GRID_H / 2 - wy / CELL_M))
    return max(0, min(GRID_W - 1, gx)), max(0, min(GRID_H - 1, gy))


# ━━ 빈 배정 ━━
def assign_bins():
    assignments = [[] for _ in range(NUM_ROBOTS)]
    remaining = list(BIN_POSITIONS)
    robot_pos = [CHARGING_STATIONS[i] for i in range(NUM_ROBOTS)]
    while remaining:
        for rid in range(NUM_ROBOTS):
            if not remaining:
                break
            last = assignments[rid][-1][:2] if assignments[rid] else robot_pos[rid]
            nearest_idx = min(range(len(remaining)),
                              key=lambda i: abs(remaining[i][0] - last[0]) + abs(remaining[i][1] - last[1]))
            assignments[rid].append(remaining.pop(nearest_idx))
    return assignments


# ━━ HTTP ━━
def send_state(data):
    try:
        req = urllib.request.Request(
            BACKEND_URL,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST')
        urllib.request.urlopen(req, timeout=0.5)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 로봇 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ProtoBot:
    def __init__(self, robot, robot_id, name, color):
        self.robot = robot
        self.id = robot_id
        self.name = name
        self.color = color
        self.timestep = int(robot.getBasicTimeStep())
        self.dt = self.timestep / 1000.0

        # 디바이스
        self.left_motor = self.right_motor = None
        self.gps = self.compass = None
        self.ultrasonics = []
        self._init_devices()

        # 물리
        self.wheel_radius = 0.04
        self.max_angular = MAX_VEL / self.wheel_radius

        # 미션
        self.state = State.IDLE
        self.battery = 100.0
        self.grid = build_grid()
        self.assigned_bins = []
        self.current_bin_idx = 0
        self.collected = []
        self.path = []
        self.path_idx = 0
        self.distance = 0.0
        self.phase = "idle"
        self.collect_timer = 0

        # 스톨 복구
        self.recovery = Recovery.NONE
        self.recovery_timer = 0
        self.recovery_dir = 1  # 회전 방향
        self.stall_pos = (0, 0)
        self.stall_timer = 0
        self.last_replan_time = 0
        self.sim_time = 0

        # 전송
        self.last_send = 0
        self.last_pos = None

        cs = CHARGING_STATIONS[robot_id - 1]
        self.cs_grid = cs
        self.start_pos = grid_to_world(*cs)

    def _init_devices(self):
        try:
            self.left_motor = self.robot.getDevice('left_wheel_motor')
            self.right_motor = self.robot.getDevice('right_wheel_motor')
            for m in [self.left_motor, self.right_motor]:
                m.setPosition(float('inf'))
                m.setVelocity(0)
        except Exception:
            pass
        try:
            self.gps = self.robot.getDevice('gps')
            self.gps.enable(self.timestep)
        except Exception:
            pass
        try:
            self.compass = self.robot.getDevice('compass')
            self.compass.enable(self.timestep)
        except Exception:
            pass
        for name in US_NAMES:
            try:
                s = self.robot.getDevice(name)
                s.enable(self.timestep)
                self.ultrasonics.append(s)
            except Exception:
                self.ultrasonics.append(None)

    # ── 센서 ──
    def pos(self):
        if self.gps:
            p = self.gps.getValues()
            if not (math.isnan(p[0]) or math.isnan(p[1])):
                return p[0], p[1]
        return self.start_pos

    def heading(self):
        if self.compass:
            c = self.compass.getValues()
            if not (math.isnan(c[0]) or math.isnan(c[1])):
                return math.atan2(c[0], c[1])
        return 0.0

    def us_min(self):
        vals = []
        for s in self.ultrasonics:
            if s:
                v = s.getValue()
                if not math.isnan(v):
                    vals.append(v)
        return min(vals) if vals else 10.0

    def us_front_min(self):
        """전방 2개 센서만."""
        vals = []
        for i in range(min(2, len(self.ultrasonics))):
            s = self.ultrasonics[i]
            if s:
                v = s.getValue()
                if not math.isnan(v):
                    vals.append(v)
        return min(vals) if vals else 10.0

    # ── 모터 ──
    def set_vel(self, vl, vr):
        if self.left_motor and self.right_motor:
            lv = max(-self.max_angular, min(self.max_angular, vl / self.wheel_radius))
            rv = max(-self.max_angular, min(self.max_angular, vr / self.wheel_radius))
            self.left_motor.setVelocity(lv)
            self.right_motor.setVelocity(rv)

    def stop(self):
        self.set_vel(0, 0)

    # ── 미션 ──
    def start_mission(self):
        all_a = assign_bins()
        self.assigned_bins = all_a[self.id - 1]
        if self.assigned_bins:
            self.state = State.NAV_TO_BIN
            self.phase = "to_bin"
            self._plan_to_current_bin()

    def _plan_to_current_bin(self):
        if self.current_bin_idx >= len(self.assigned_bins):
            self._plan_to_cp()
            return
        bx, by, _ = self.assigned_bins[self.current_bin_idx]
        gx, gy = world_to_grid(*self.pos())
        path = astar(self.grid, (gx, gy), (bx, by))
        self.path = simplify_path(path) if path else []
        self.path_idx = 0

    def _plan_to_cp(self):
        gx, gy = world_to_grid(*self.pos())
        path = astar(self.grid, (gx, gy), CP)
        self.path = simplify_path(path) if path else []
        self.path_idx = 0
        self.state = State.NAV_TO_CP
        self.phase = "to_cp"

    def _replan(self):
        """현재 목표로 경로 재탐색."""
        if self.sim_time - self.last_replan_time < REPLAN_COOLDOWN:
            return
        self.last_replan_time = self.sim_time
        if self.phase == "to_bin":
            self._plan_to_current_bin()
        elif self.phase == "to_cp":
            self._plan_to_cp()
        elif self.phase == "charging":
            gx, gy = world_to_grid(*self.pos())
            path = astar(self.grid, (gx, gy), self.cs_grid)
            self.path = simplify_path(path) if path else []
            self.path_idx = 0

    # ── 메인 루프 ──
    def update(self):
        self.sim_time += self.dt

        # 수거 중
        if self.state == State.COLLECTING:
            self.stop()
            self.collect_timer -= self.dt
            if self.collect_timer <= 0:
                if self.current_bin_idx < len(self.assigned_bins):
                    self.state = State.NAV_TO_BIN
                    self.phase = "to_bin"
                    self._plan_to_current_bin()
                else:
                    self._plan_to_cp()
            self._send()
            return

        # 완료/충전 중
        if self.phase == "done":
            self.stop()
            self._send()
            return

        # 배터리 부족
        if self.battery <= BATTERY_LOW and self.phase not in ("charging", "done"):
            gx, gy = world_to_grid(*self.pos())
            path = astar(self.grid, (gx, gy), self.cs_grid)
            self.path = simplify_path(path) if path else []
            self.path_idx = 0
            self.state = State.CHARGING
            self.phase = "charging"

        # ── 스톨 복구 모드 ──
        if self.recovery != Recovery.NONE:
            self.recovery_timer -= self.dt
            if self.recovery_timer <= 0:
                if self.recovery == Recovery.REVERSE:
                    # 후진 끝 → 회전
                    self.recovery = Recovery.TURN
                    self.recovery_timer = TURN_TIME
                    self.recovery_dir = 1 if (self.id % 2 == 0) else -1  # 로봇별 다른 방향
                elif self.recovery == Recovery.TURN:
                    # 회전 끝 → 재경로
                    self.recovery = Recovery.NONE
                    self._replan()
            else:
                if self.recovery == Recovery.REVERSE:
                    self.set_vel(-MAX_VEL * 0.5, -MAX_VEL * 0.5)
                elif self.recovery == Recovery.TURN:
                    self.set_vel(MAX_VEL * 0.4 * self.recovery_dir,
                                -MAX_VEL * 0.4 * self.recovery_dir)
            self._update_distance()
            self._send()
            return

        # ── 경로 추종 (제자리 회전 → 직진) ──
        if self.path_idx < len(self.path):
            target = self.path[self.path_idx]
            tx, ty = grid_to_world(*target)
            cx, cy = self.pos()
            dx, dy = tx - cx, ty - cy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < WAYPOINT_REACH:
                self.path_idx += 1
                self.stall_timer = 0
                self.stall_pos = self.pos()
                self.stop()
                if self.path_idx >= len(self.path):
                    self._on_arrive()
            else:
                # 초음파 — 벽 감지
                front = self.us_front_min()
                if front < US_STOP:
                    self.stop()
                    self.recovery = Recovery.REVERSE
                    self.recovery_timer = REVERSE_TIME
                    self._send()
                    return

                # 방향 계산
                h = self.heading()
                target_h = math.atan2(dy, dx)
                err = target_h - h
                while err > math.pi: err -= 2 * math.pi
                while err < -math.pi: err += 2 * math.pi

                TURN_THRESHOLD = 0.3  # ~17도 이내면 직진

                if abs(err) > TURN_THRESHOLD:
                    # ── 제자리 회전 ──
                    turn_speed = MAX_VEL * 0.4
                    if err > 0:
                        self.set_vel(-turn_speed, turn_speed)   # 좌회전
                    else:
                        self.set_vel(turn_speed, -turn_speed)   # 우회전
                else:
                    # ── 직진 ──
                    speed = MAX_VEL
                    if front < US_SLOW:
                        speed *= max(0.2, (front - US_STOP) / (US_SLOW - US_STOP))
                    self.set_vel(speed, speed)

                # 스톨 감지
                cp_ = self.pos()
                moved = math.sqrt((cp_[0] - self.stall_pos[0]) ** 2 + (cp_[1] - self.stall_pos[1]) ** 2)
                if moved < STALL_DIST:
                    self.stall_timer += self.dt
                    if self.stall_timer > STALL_TIME:
                        self.stall_timer = 0
                        self.stall_pos = cp_
                        self.recovery = Recovery.REVERSE
                        self.recovery_timer = REVERSE_TIME
                else:
                    self.stall_timer = 0
                    self.stall_pos = cp_
        else:
            self.stop()

        self._update_distance()
        self._send()

    def _on_arrive(self):
        self.stop()
        if self.phase == "to_bin":
            code = self.assigned_bins[self.current_bin_idx][2]
            self.collected.append(code)
            self.current_bin_idx += 1
            self.state = State.COLLECTING
            self.collect_timer = COLLECT_SEC
        elif self.phase == "to_cp":
            self.state = State.DONE
            self.phase = "done"
        elif self.phase == "charging":
            self.state = State.IDLE
            self.phase = "done"

    def _update_distance(self):
        cp_ = self.pos()
        if self.last_pos:
            d = math.sqrt((cp_[0] - self.last_pos[0]) ** 2 + (cp_[1] - self.last_pos[1]) ** 2)
            self.distance += d
            self.battery = max(0, self.battery - d * BATTERY_DRAIN)
        self.last_pos = cp_

    def _send(self):
        self.last_send += self.dt
        if self.last_send < SEND_INTERVAL:
            return
        self.last_send = 0
        gx, gy = world_to_grid(*self.pos())
        cur_bin = None
        if self.phase == "to_bin" and self.current_bin_idx < len(self.assigned_bins):
            cur_bin = self.assigned_bins[self.current_bin_idx][2]
        send_state({
            "robot_id": self.id,
            "name": self.name,
            "color": self.color,
            "x": gx, "y": gy,
            "battery": round(self.battery, 1),
            "state": self.state.value,
            "phase": self.phase,
            "assigned_bins": [b[2] for b in self.assigned_bins],
            "collected_bins": self.collected,
            "current_bin": cur_bin,
            "distance": round(self.distance, 2),
        })


# ━━ main ━━
def main():
    robot = Robot()
    timestep = int(robot.getBasicTimeStep())
    name = robot.getName()
    print(f"[Prototype] 로봇: {name}")

    if "A" in name or name.endswith("1"):
        rid, rname, color = 1, "로봇-A", "#ef4444"
    else:
        rid, rname, color = 2, "로봇-B", "#3b82f6"

    # 센서 워밍업
    for _ in range(10):
        if robot.step(timestep) == -1:
            return

    bot = ProtoBot(robot, rid, rname, color)
    print(f"[{rname}] GPS: {bot.pos()}")

    bot.start_mission()
    print(f"[{rname}] 미션 시작 — {len(bot.assigned_bins)}개")

    while robot.step(timestep) != -1:
        bot.update()


if __name__ == "__main__":
    main()
