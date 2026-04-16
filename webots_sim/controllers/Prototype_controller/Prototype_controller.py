"""시제품 Webots 컨트롤러 v3 — 가속도 + 수거→수거함 흐름."""
import math
import heapq
import json
import os
import urllib.request
from enum import Enum
from controller import Supervisor

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/webots-prototype/state")
SEND_INTERVAL = 0.2

GRID_W, GRID_H = 40, 30
CELL_M = 0.5
CP = (20, 27)
NUM_ROBOTS = 2

MAX_VEL = 2.0         # 최대 속도
ACCEL = 1.5            # 가속도 (m/s²) — 점진적 가속
DECEL = 3.0            # 감속 (m/s²)
WAYPOINT_REACH = 0.5
TURN_THRESHOLD = 0.25  # ~14도
COLLECT_SEC = 1.5
BATTERY_DRAIN = 0.05
BATTERY_LOW = 15.0
US_STOP = 0.08      # 8cm — 거의 부딪힐 때만 정지
US_SLOW = 0.15       # 15cm — 가까울 때만 감속
STALL_DIST = 0.02
STALL_TIME = 3.0      # 충분히 기다린 후에만 복구
REVERSE_TIME = 0.3     # 짧게 후진
TURN_TIME = 0.3        # 짧게 회전
REPLAN_COOLDOWN = 2.0

BIN_POSITIONS = [
    (11, 8, "BIN-01"), (26, 8, "BIN-02"),
    (11, 21, "BIN-03"), (26, 21, "BIN-04"),
]
CHARGING_STATIONS = [(3, 26), (36, 26)]
US_NAMES = ['us_front_left', 'us_front_right',
            'us_side_left', 'us_side_right', 'us_rear']


class State(Enum):
    IDLE = "대기"
    TO_BIN = "이동중"
    PICKUP = "수거중"
    TO_CP = "복귀중"
    DROP = "내려놓는중"
    DONE = "완료"


class Recovery(Enum):
    NONE = 0; REVERSE = 1; TURN = 2


def build_grid():
    grid = [[0]*GRID_W for _ in range(GRID_H)]
    def w(x1,y1,x2,y2):
        for y in range(y1,min(y2+1,GRID_H)):
            for x in range(x1,min(x2+1,GRID_W)):
                grid[y][x]=1
    for x in range(GRID_W): grid[0][x]=1; grid[GRID_H-1][x]=1
    for y in range(GRID_H): grid[y][0]=1; grid[y][GRID_W-1]=1
    w(4,3,9,7); w(27,3,32,7); w(4,16,9,20); w(27,16,32,20)
    w(16,11,21,13); w(14,23,23,25); w(19,28,20,28)
    return grid


def astar(grid, start, goal):
    sx,sy=start; gx,gy=goal
    if sx==gx and sy==gy: return [goal]
    dirs=[(0,1),(0,-1),(1,0),(-1,0)]
    heap=[(abs(gx-sx)+abs(gy-sy),0,sx,sy)]
    g_sc={(sx,sy):0}; parent={}; closed=set()
    while heap:
        _,g,cx,cy=heapq.heappop(heap)
        if (cx,cy) in closed: continue
        closed.add((cx,cy))
        if cx==gx and cy==gy:
            p=[]; c=(gx,gy)
            while c in parent: p.append(c); c=parent[c]
            p.append(start); p.reverse(); return p
        for dx,dy in dirs:
            nx,ny=cx+dx,cy+dy
            if 0<=nx<GRID_W and 0<=ny<GRID_H and grid[ny][nx]==0:
                ng=g+1
                if ng<g_sc.get((nx,ny),float('inf')):
                    g_sc[(nx,ny)]=ng; parent[(nx,ny)]=(cx,cy)
                    heapq.heappush(heap,(ng+abs(gx-nx)+abs(gy-ny),ng,nx,ny))
    return []


def grid_to_world(gx,gy):
    return (gx-GRID_W/2)*CELL_M, (GRID_H/2-gy)*CELL_M

def world_to_grid(wx,wy):
    return max(0,min(GRID_W-1,int(round(wx/CELL_M+GRID_W/2)))), max(0,min(GRID_H-1,int(round(GRID_H/2-wy/CELL_M))))


def assign_bins():
    a=[[] for _ in range(NUM_ROBOTS)]
    rem=list(BIN_POSITIONS)
    rp=[CHARGING_STATIONS[i] for i in range(NUM_ROBOTS)]
    while rem:
        for r in range(NUM_ROBOTS):
            if not rem: break
            last=a[r][-1][:2] if a[r] else rp[r]
            ni=min(range(len(rem)),key=lambda i:abs(rem[i][0]-last[0])+abs(rem[i][1]-last[1]))
            a[r].append(rem.pop(ni))
    return a


def send_state(data):
    try:
        req=urllib.request.Request(BACKEND_URL,data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type':'application/json'},method='POST')
        urllib.request.urlopen(req,timeout=0.5)
    except: pass


class ProtoBot:
    def __init__(self, robot, rid, name, color):
        self.robot = robot
        self.id = rid
        self.name = name
        self.color = color
        self.ts = int(robot.getBasicTimeStep())
        self.dt = self.ts / 1000.0
        self.wr = 0.04  # wheel radius
        self.max_w = MAX_VEL / self.wr

        # devices
        self.lm = self.rm = None
        self.gps = self.compass = None
        self.us = []
        self._init_dev()

        # bin nodes (supervisor)
        self.bin_nodes = {}
        for _,_,code in BIN_POSITIONS:
            n = robot.getFromDef(code.replace("-","_"))
            if n: self.bin_nodes[code] = n

        # state
        self.state = State.IDLE
        self.carrying = None
        self.collected = []
        self.assigned = []
        self.bin_idx = 0
        self.path = []
        self.path_i = 0
        self.grid = build_grid()

        self.battery = 100.0
        self.dist = 0.0
        self.cur_speed = 0.0  # 현재 속도 (가속도용)
        self.timer = 0
        self.sim_t = 0
        self.last_send = 0
        self.last_pos = None
        self.stall_pos = (0,0)
        self.stall_t = 0
        self.last_replan = 0

        self.rec = Recovery.NONE
        self.rec_timer = 0
        self.rec_dir = 1

        cs = CHARGING_STATIONS[rid-1]
        self.cs = cs
        self.start = grid_to_world(*cs)

    def _init_dev(self):
        try:
            self.lm=self.robot.getDevice('left_wheel_motor')
            self.rm=self.robot.getDevice('right_wheel_motor')
            for m in [self.lm,self.rm]: m.setPosition(float('inf')); m.setVelocity(0)
        except: pass
        try:
            self.gps=self.robot.getDevice('gps'); self.gps.enable(self.ts)
        except: pass
        try:
            self.compass=self.robot.getDevice('compass'); self.compass.enable(self.ts)
        except: pass
        for n in US_NAMES:
            try:
                s=self.robot.getDevice(n); s.enable(self.ts); self.us.append(s)
            except: self.us.append(None)

    def pos(self):
        if self.gps:
            p=self.gps.getValues()
            if not(math.isnan(p[0]) or math.isnan(p[1])): return p[0],p[1]
        return self.start

    def heading(self):
        if self.compass:
            c=self.compass.getValues()
            if not(math.isnan(c[0]) or math.isnan(c[1])): return math.atan2(c[0],c[1])
        return 0.0

    def us_front(self):
        v=[]
        for i in range(min(2,len(self.us))):
            if self.us[i]:
                val=self.us[i].getValue()
                if not math.isnan(val): v.append(val)
        return min(v) if v else 10.0

    def vel(self,vl,vr):
        if self.lm and self.rm:
            self.lm.setVelocity(max(-self.max_w,min(self.max_w,vl/self.wr)))
            self.rm.setVelocity(max(-self.max_w,min(self.max_w,vr/self.wr)))

    def stop(self):
        self.vel(0,0); self.cur_speed=0

    # ── 경로 ──
    def plan_to(self, goal):
        g = world_to_grid(*self.pos())
        self.path = astar(self.grid, g, goal)
        self.path_i = 0
        self.stall_pos = self.pos()
        self.stall_t = 0
        self.cur_speed = 0

    def start_mission(self):
        a = assign_bins()
        self.assigned = a[self.id-1]
        if self.assigned:
            self.state = State.TO_BIN
            bx,by,_ = self.assigned[0]
            self.plan_to((bx,by))

    def _replan(self):
        if self.sim_t - self.last_replan < REPLAN_COOLDOWN: return
        self.last_replan = self.sim_t
        if self.state == State.TO_BIN and self.bin_idx < len(self.assigned):
            bx,by,_ = self.assigned[self.bin_idx]
            self.plan_to((bx,by))
        elif self.state == State.TO_CP:
            self.plan_to(CP)

    # ── 메인 ──
    def update(self):
        self.sim_t += self.dt

        # ── PICKUP (들어올리기 대기) ──
        if self.state == State.PICKUP:
            self.stop()
            self._move_carried_bin()
            self.timer -= self.dt
            if self.timer <= 0:
                # 수거함으로
                self.state = State.TO_CP
                self.plan_to(CP)
                print(f"[{self.name}] → 수거함 ({len(self.path)}셀)")
            self._dist(); self._tx()
            return

        # ── DROP (내려놓기 대기) ──
        if self.state == State.DROP:
            self.stop()
            self.timer -= self.dt
            if self.timer <= 0:
                # 빈 내려놓기
                if self.carrying:
                    node = self.bin_nodes.get(self.carrying)
                    if node:
                        cpx,cpy = grid_to_world(*CP)
                        off = len(self.collected) * 0.4
                        node.getField("translation").setSFVec3f([cpx-0.6+off, cpy-0.5, 0.08])
                    self.collected.append(self.carrying)
                    print(f"[{self.name}] {self.carrying} 내려놓음 ({len(self.collected)}개)")
                    self.carrying = None

                self.bin_idx += 1
                if self.bin_idx < len(self.assigned):
                    self.state = State.TO_BIN
                    bx,by,_ = self.assigned[self.bin_idx]
                    self.plan_to((bx,by))
                    print(f"[{self.name}] → 다음 빈 {self.assigned[self.bin_idx][2]}")
                else:
                    self.state = State.DONE
                    print(f"[{self.name}] 미션 완료! ({len(self.collected)}개)")
            self._dist(); self._tx()
            return

        # ── DONE ──
        if self.state == State.DONE:
            self.stop(); self._tx(); return

        # ── 스톨 복구 ──
        if self.rec != Recovery.NONE:
            self.rec_timer -= self.dt
            if self.rec_timer <= 0:
                if self.rec == Recovery.REVERSE:
                    self.rec = Recovery.TURN
                    self.rec_timer = TURN_TIME
                    self.rec_dir = 1 if self.id%2==0 else -1
                else:
                    self.rec = Recovery.NONE
                    self._replan()
            else:
                if self.rec == Recovery.REVERSE:
                    self.vel(-MAX_VEL*0.4, -MAX_VEL*0.4)
                else:
                    self.vel(MAX_VEL*0.3*self.rec_dir, -MAX_VEL*0.3*self.rec_dir)
            self._move_carried_bin(); self._dist(); self._tx()
            return

        # ── 경로 추종 ──
        if self.path_i < len(self.path):
            tgt = self.path[self.path_i]
            tx,ty = grid_to_world(*tgt)
            cx,cy = self.pos()
            dx,dy = tx-cx, ty-cy
            d = math.sqrt(dx*dx+dy*dy)

            if d < WAYPOINT_REACH:
                self.path_i += 1
                self.stall_t = 0
                self.stall_pos = self.pos()
                if self.path_i >= len(self.path):
                    self._arrive()
            else:
                front = self.us_front()
                if front < US_STOP:
                    self.stop()
                    self.rec = Recovery.REVERSE
                    self.rec_timer = REVERSE_TIME
                    self._move_carried_bin(); self._dist(); self._tx()
                    return

                h = self.heading()
                th = math.atan2(dy, dx)
                err = th - h
                while err > math.pi: err -= 2*math.pi
                while err < -math.pi: err += 2*math.pi

                abs_err = abs(err)
                remaining_cells = len(self.path) - self.path_i
                near_target = remaining_cells <= 3

                if abs_err > 2.8:
                    # 목표가 거의 정 뒤 (>160°) → 후진
                    target_speed = MAX_VEL * (0.25 if near_target else 0.5)
                    if self.cur_speed > 0:
                        self.cur_speed = max(0, self.cur_speed - DECEL * self.dt)
                    else:
                        self.cur_speed = max(-target_speed, self.cur_speed - ACCEL * self.dt * 0.5)
                    self.vel(self.cur_speed, self.cur_speed)

                elif abs_err > TURN_THRESHOLD:
                    # 방향 틀어짐 → 제자리 회전
                    self.cur_speed = 0
                    ts = MAX_VEL * 0.3
                    if err > 0: self.vel(-ts, ts)
                    else: self.vel(ts, -ts)

                else:
                    # 전진
                    if near_target:
                        target_speed = MAX_VEL * 0.3
                    else:
                        target_speed = MAX_VEL

                    if front < US_SLOW:
                        target_speed = min(target_speed, MAX_VEL * 0.3)

                    if self.cur_speed < 0:
                        self.cur_speed = min(0, self.cur_speed + DECEL * self.dt)
                    elif self.cur_speed < target_speed:
                        self.cur_speed = min(target_speed, self.cur_speed + ACCEL * self.dt)
                    elif self.cur_speed > target_speed:
                        self.cur_speed = max(target_speed, self.cur_speed - DECEL * self.dt)

                    self.vel(self.cur_speed, self.cur_speed)

                # 스톨
                cp_ = self.pos()
                mv = math.sqrt((cp_[0]-self.stall_pos[0])**2+(cp_[1]-self.stall_pos[1])**2)
                if mv < STALL_DIST:
                    self.stall_t += self.dt
                    if self.stall_t > STALL_TIME:
                        self.stall_t=0; self.stall_pos=cp_
                        self.rec=Recovery.REVERSE; self.rec_timer=REVERSE_TIME
                else:
                    self.stall_t=0; self.stall_pos=cp_
        else:
            self.stop()

        self._move_carried_bin()
        self._dist(); self._tx()

    def _arrive(self):
        self.stop()
        if self.state == State.TO_BIN:
            code = self.assigned[self.bin_idx][2]
            self.carrying = code
            self.state = State.PICKUP
            self.timer = COLLECT_SEC
            # 빈을 맵 밖으로 (충돌 방지 — 물리적으로 치우기)
            n = self.bin_nodes.get(code)
            if n:
                n.getField("translation").setSFVec3f([0, 0, -10])
            print(f"[{self.name}] {code} 들어올림")

        elif self.state == State.TO_CP:
            self.state = State.DROP
            self.timer = 1.0
            print(f"[{self.name}] 수거함 도착")

    def _move_carried_bin(self):
        pass  # 빈은 맵 밖에 있으므로 위치 업데이트 불필요

    def _dist(self):
        p = self.pos()
        if self.last_pos:
            d = math.sqrt((p[0]-self.last_pos[0])**2+(p[1]-self.last_pos[1])**2)
            self.dist += d
            self.battery = max(0, self.battery - d*BATTERY_DRAIN)
        self.last_pos = p

    def _tx(self):
        self.last_send += self.dt
        if self.last_send < SEND_INTERVAL: return
        self.last_send = 0
        gx,gy = world_to_grid(*self.pos())
        cb = None
        if self.state==State.TO_BIN and self.bin_idx<len(self.assigned):
            cb = self.assigned[self.bin_idx][2]
        send_state({
            "robot_id":self.id, "name":self.name, "color":self.color,
            "x":gx, "y":gy, "battery":round(self.battery,1),
            "state":self.state.value, "phase":self.state.name.lower(),
            "assigned_bins":[b[2] for b in self.assigned],
            "collected_bins":self.collected, "current_bin":cb,
            "carrying_bin":self.carrying,
            "distance":round(self.dist,2),
        })


def main():
    robot = Supervisor()
    ts = int(robot.getBasicTimeStep())
    name = robot.getName()
    print(f"[Proto] {name}")

    if "A" in name or name.endswith("1"):
        rid,rn,col = 1,"로봇-A","#ef4444"
    else:
        rid,rn,col = 2,"로봇-B","#3b82f6"

    for _ in range(10):
        if robot.step(ts)==-1: return

    bot = ProtoBot(robot, rid, rn, col)
    print(f"[{rn}] GPS:{bot.pos()} → 미션 시작")
    bot.start_mission()

    while robot.step(ts) != -1:
        bot.update()


if __name__ == "__main__":
    main()
