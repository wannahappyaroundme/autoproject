"""
논문용 정량 실험 — 실제 백엔드 알고리즘(astar, optimize_visit_order)을 그대로 실행해
재현 가능한 수치를 생성한다. 데이터를 임의로 만들지 않고 코드를 실행한 결과만 보고한다.

실행:
    cd backend && source ../.venv/bin/activate
    python ../tools/run_experiments.py
출력:
    tools/experiments_results.json  (표/본문에 인용)
"""
import json
import math
import os
import random
import sys
import time
from itertools import permutations

# 백엔드 순수 알고리즘 모듈 import
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from services.pathfinding import astar          # noqa: E402
from services.mission_planner import optimize_visit_order  # noqa: E402

random.seed(42)  # 재현성

# ---------- 프로덕션과 동일한 시제품 맵 (simulation_prototype.py 그대로) ----------
MAP_WIDTH, MAP_HEIGHT = 40, 30
COLLECTION_POINT = (20.0, 27.0)
BINS = {1: (11, 8), 2: (26, 8), 3: (11, 21), 4: (26, 21)}
ROBOT_START = {"A": (3, 26), "B": (36, 26)}  # CS-1, CS-2
ROBOT_SPEED = 0.3   # cells/s (시제품 NP01D-288 기준)
PICKUP_TIME = 3.0   # s/bin


def build_grid():
    grid = [[0] * MAP_WIDTH for _ in range(MAP_HEIGHT)]

    def wall(x1, y1, x2, y2):
        for y in range(y1, min(y2 + 1, MAP_HEIGHT)):
            for x in range(x1, min(x2 + 1, MAP_WIDTH)):
                grid[y][x] = 1

    for x in range(MAP_WIDTH):
        grid[0][x] = 1
        grid[MAP_HEIGHT - 1][x] = 1
    for y in range(MAP_HEIGHT):
        grid[y][0] = 1
        grid[y][MAP_WIDTH - 1] = 1
    wall(4, 3, 9, 7)
    wall(27, 3, 32, 7)
    wall(4, 16, 9, 20)
    wall(27, 16, 32, 20)
    wall(16, 11, 21, 13)
    wall(14, 23, 23, 25)
    wall(19, 28, 20, 28)
    return grid


GRID = build_grid()
OBSTACLES = [(x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH) if GRID[y][x] == 1]
FREE = [(x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH) if GRID[y][x] == 0]


def path_len(path):
    return sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1))


def clearance(path):
    """경로 셀들의 최소/평균 장애물 이격거리 [cells]."""
    ds = []
    for (px, py) in path:
        d = min(math.dist((px, py), o) for o in OBSTACLES)
        ds.append(d)
    return min(ds), sum(ds) / len(ds)


def time_astar(grid, s, g, infl, repeats=200):
    t0 = time.perf_counter()
    for _ in range(repeats):
        p = astar(grid, s, g, len(grid[0]), len(grid), inflation_radius=infl)
    dt = (time.perf_counter() - t0) / repeats
    return p, dt


# ====================================================================
# E1. 미션 KPI — 프로덕션 /plan 로직 재현
# ====================================================================
def mission_plan(start, bin_ids, infl=2):
    bin_pos = {b: BINS[b] for b in bin_ids}
    order = optimize_visit_order(start, bin_pos)
    wps = [start] + [bin_pos[b] for b in order] + [COLLECTION_POINT]
    total = 0.0
    legs = []
    for i in range(len(wps) - 1):
        s = (int(wps[i][0]), int(wps[i][1]))
        g = (int(wps[i + 1][0]), int(wps[i + 1][1]))
        p = astar(GRID, s, g, MAP_WIDTH, MAP_HEIGHT, inflation_radius=infl) or [s, g]
        d = path_len(p)
        total += d
        legs.append({"from": s, "to": g, "dist": round(d, 2), "cells": len(p)})
    est = total / ROBOT_SPEED + len(order) * PICKUP_TIME
    return {"order": order, "total_distance": round(total, 2),
            "est_time_sec": round(est, 1), "legs": legs}


def exp1():
    single = mission_plan(COLLECTION_POINT, [1, 2, 3, 4])
    # 2로봇 분담: A=좌측(1,3) from CS-1, B=우측(2,4) from CS-2
    a = mission_plan(ROBOT_START["A"], [1, 3])
    b = mission_plan(ROBOT_START["B"], [2, 4])
    makespan = max(a["est_time_sec"], b["est_time_sec"])
    return {
        "single_robot_all4": single,
        "dual_robot": {"robotA_left": a, "robotB_right": b,
                       "makespan_sec": round(makespan, 1),
                       "throughput_improvement_pct": round(
                           (single["est_time_sec"] - makespan) / single["est_time_sec"] * 100, 1)},
    }


# ====================================================================
# E2. Inflation radius 민감도
# ====================================================================
def exp2():
    rows = []
    for infl in [0, 1, 2, 3, 4]:
        # full single-robot mission legs 합산
        bin_pos = {b: BINS[b] for b in [1, 2, 3, 4]}
        order = optimize_visit_order(COLLECTION_POINT, bin_pos)
        wps = [COLLECTION_POINT] + [bin_pos[b] for b in order] + [COLLECTION_POINT]
        tot_len, mins, means, tsum = 0.0, [], [], 0.0
        for i in range(len(wps) - 1):
            s = (int(wps[i][0]), int(wps[i][1]))
            g = (int(wps[i + 1][0]), int(wps[i + 1][1]))
            p, dt = time_astar(GRID, s, g, infl, repeats=100)
            p = p or [s, g]
            tot_len += path_len(p)
            cmin, cmean = clearance(p)
            mins.append(cmin); means.append(cmean); tsum += dt
        rows.append({
            "inflation_radius": infl,
            "total_path_len": round(tot_len, 2),
            "min_clearance_cells": round(min(mins), 2),
            "mean_clearance_cells": round(sum(means) / len(means), 2),
            "avg_astar_ms": round(tsum / (len(wps) - 1) * 1000, 3),
        })
    return rows


# ====================================================================
# E3. TSP nearest-neighbor 품질 (vs 완전탐색 최적)
# ====================================================================
def astar_dist(a, b, cache):
    key = (a, b)
    if key in cache:
        return cache[key]
    p = astar(GRID, a, b, MAP_WIDTH, MAP_HEIGHT, inflation_radius=2) or [a, b]
    cache[key] = cache[(b, a)] = path_len(p)
    return cache[key]


def route_cost(start, order, cache):
    cost, cur = 0.0, start
    for n in order:
        cost += astar_dist(cur, n, cache); cur = n
    cost += astar_dist(cur, start, cache)  # depot 복귀
    return cost


def exp3():
    out = []
    # (a) 실제 4-bin 레이아웃
    cache = {}
    start = (int(COLLECTION_POINT[0]), int(COLLECTION_POINT[1]))
    nodes = [BINS[b] for b in [1, 2, 3, 4]]
    nn = optimize_visit_order(COLLECTION_POINT, {b: BINS[b] for b in [1, 2, 3, 4]})
    nn_nodes = [BINS[b] for b in nn]
    nn_cost = route_cost(start, nn_nodes, cache)
    opt = min(route_cost(start, list(p), cache) for p in permutations(nodes))
    out.append({"case": "real_4bin", "N": 4, "nn_cost": round(nn_cost, 2),
                "opt_cost": round(opt, 2),
                "gap_pct": round((nn_cost - opt) / opt * 100, 2)})
    # (b) 랜덤 인스턴스 N=4..8 (NN heuristic 평균 최적성 격차)
    for N in [4, 5, 6, 7, 8]:
        gaps = []
        K = 30
        for _ in range(K):
            pts = random.sample(FREE, N)
            cache = {}
            sp = random.choice(FREE)
            bp = {i: pts[i] for i in range(N)}
            nn_order = optimize_visit_order(sp, bp)
            nn_nodes = [bp[i] for i in nn_order]
            nn_c = route_cost(sp, nn_nodes, cache)
            opt_c = min(route_cost(sp, list(p), cache) for p in permutations(pts))
            gaps.append((nn_c - opt_c) / opt_c * 100)
        out.append({"case": "random", "N": N, "instances": K,
                    "mean_gap_pct": round(sum(gaps) / len(gaps), 2),
                    "max_gap_pct": round(max(gaps), 2)})
    return out


# ====================================================================
# E4. A* 확장성 (격자 크기 vs 계산시간)
# ====================================================================
def exp4():
    rows = []
    for w, h in [(40, 30), (80, 60), (120, 90), (160, 120), (200, 140)]:
        g = [[0] * w for _ in range(h)]
        for x in range(w):
            g[0][x] = 1; g[h - 1][x] = 1
        for y in range(h):
            g[y][0] = 1; g[y][w - 1] = 1
        s, gl = (1, 1), (w - 2, h - 2)
        t0 = time.perf_counter()
        R = 20
        for _ in range(R):
            p = astar(g, s, gl, w, h, inflation_radius=2)
        dt = (time.perf_counter() - t0) / R
        rows.append({"grid": f"{w}x{h}", "cells": w * h,
                     "path_cells": len(p), "path_len": round(path_len(p), 2),
                     "avg_time_ms": round(dt * 1000, 3)})
    return rows


if __name__ == "__main__":
    results = {
        "meta": {"grid": f"{MAP_WIDTH}x{MAP_HEIGHT}", "n_obstacles": len(OBSTACLES),
                 "robot_speed_cells_s": ROBOT_SPEED, "pickup_time_s": PICKUP_TIME,
                 "seed": 42},
        "E1_mission_kpi": exp1(),
        "E2_inflation": exp2(),
        "E3_tsp_quality": exp3(),
        "E4_scalability": exp4(),
    }
    outp = os.path.join(HERE, "experiments_results.json")
    with open(outp, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("\nsaved:", outp)
