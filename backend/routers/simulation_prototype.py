"""시제품 테스트용 시뮬레이션 라우터 — 30×20 소형 맵."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Bin
from schemas import SimulationPlanRequest, SimulationPlanResponse, PathSegment
from services.pathfinding import astar
from services.mission_planner import optimize_visit_order

router = APIRouter(prefix="/api/simulation-prototype", tags=["simulation-prototype"])

# 소형 아파트 단지 테스트장: 40×30 그리드
MAP_WIDTH = 40
MAP_HEIGHT = 30
COLLECTION_POINT = (20.0, 27.0)


def get_prototype_map() -> list[list[int]]:
    grid = [[0] * MAP_WIDTH for _ in range(MAP_HEIGHT)]

    def wall(x1: int, y1: int, x2: int, y2: int):
        for y in range(y1, min(y2 + 1, MAP_HEIGHT)):
            for x in range(x1, min(x2 + 1, MAP_WIDTH)):
                grid[y][x] = 1

    # 외벽 (단지 경계)
    for x in range(MAP_WIDTH):
        grid[0][x] = 1
        grid[MAP_HEIGHT - 1][x] = 1
    for y in range(MAP_HEIGHT):
        grid[y][0] = 1
        grid[y][MAP_WIDTH - 1] = 1

    # 건물 4동 (양쪽 대칭)
    wall(4, 3, 9, 7)      # 101동
    wall(27, 3, 32, 7)    # 102동
    wall(4, 16, 9, 20)    # 103동
    wall(27, 16, 32, 20)  # 104동
    # 놀이터 (중앙)
    wall(16, 11, 21, 13)
    # 주차장 (하단 중앙)
    wall(14, 23, 23, 25)
    # 경비실
    wall(19, 28, 20, 28)

    return grid


@router.get("/map")
async def get_map():
    grid = get_prototype_map()
    return {
        "width": MAP_WIDTH,
        "height": MAP_HEIGHT,
        "grid": grid,
        "collection_point": COLLECTION_POINT,
    }


@router.post("/plan", response_model=SimulationPlanResponse)
async def plan_route(req: SimulationPlanRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bin).where(Bin.id.in_(req.bin_ids)))
    bins = {b.id: b for b in result.scalars().all()}

    if not bins:
        raise HTTPException(status_code=400, detail="No valid bins found")

    bin_positions = {bid: (bins[bid].map_x, bins[bid].map_y) for bid in req.bin_ids if bid in bins}

    start = COLLECTION_POINT
    ordered_ids = optimize_visit_order(start, bin_positions)

    grid = get_prototype_map()
    waypoints = [start] + [bin_positions[bid] for bid in ordered_ids] + [COLLECTION_POINT]

    paths = []
    total_distance = 0.0
    for i in range(len(waypoints) - 1):
        sx, sy = int(waypoints[i][0]), int(waypoints[i][1])
        gx, gy = int(waypoints[i + 1][0]), int(waypoints[i + 1][1])
        path = astar(grid, (sx, sy), (gx, gy), MAP_WIDTH, MAP_HEIGHT)
        if not path:
            path = [(sx, sy), (gx, gy)]

        seg_dist = sum(
            ((path[j + 1][0] - path[j][0]) ** 2 + (path[j + 1][1] - path[j][1]) ** 2) ** 0.5
            for j in range(len(path) - 1)
        )
        total_distance += seg_dist
        paths.append(PathSegment(
            from_x=waypoints[i][0], from_y=waypoints[i][1],
            to_x=waypoints[i + 1][0], to_y=waypoints[i + 1][1],
            path=[(float(p[0]), float(p[1])) for p in path],
        ))

    robot_speed = 0.3  # 시제품 속도 (NP01D-288 기준, 느림)
    pickup_time = 3.0
    est_time = (total_distance / robot_speed) + (len(ordered_ids) * pickup_time)

    return SimulationPlanResponse(
        ordered_bin_ids=ordered_ids,
        paths=paths,
        total_distance=round(total_distance, 2),
        estimated_time_sec=round(est_time, 1),
    )
