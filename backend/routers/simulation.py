from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Bin
from schemas import SimulationPlanRequest, SimulationPlanResponse, PathSegment
from services.pathfinding import astar
from services.mission_planner import optimize_visit_order

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

# Default map: 70x50 grid (0=road, 1=building/obstacle)
MAP_WIDTH = 70
MAP_HEIGHT = 50
COLLECTION_POINT = (35.0, 0.0)


def get_default_map() -> list[list[int]]:
    grid = [[0] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    # Buildings as solid blocks
    buildings = [
        (2, 1, 8, 5), (10, 1, 16, 5),      # Row 1
        (2, 9, 8, 14), (10, 9, 16, 14),     # Row 2
        (2, 20, 8, 25), (10, 20, 16, 25),   # Row 3
        (37, 1, 43, 5), (45, 1, 51, 5),     # Area 2 Row 1
        (37, 9, 43, 14), (45, 9, 51, 14),   # Area 2 Row 2
    ]
    for x1, y1, x2, y2 in buildings:
        for y in range(y1, min(y2 + 1, MAP_HEIGHT)):
            for x in range(x1, min(x2 + 1, MAP_WIDTH)):
                grid[y][x] = 1
    return grid


@router.get("/map")
async def get_map():
    grid = get_default_map()
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

    # Get bin positions
    bin_positions = {bid: (bins[bid].map_x, bins[bid].map_y) for bid in req.bin_ids if bid in bins}

    # Optimize visit order (nearest-neighbor TSP)
    start = COLLECTION_POINT
    ordered_ids = optimize_visit_order(start, bin_positions)

    # Compute A* paths between waypoints
    grid = get_default_map()
    waypoints = [start] + [bin_positions[bid] for bid in ordered_ids] + [COLLECTION_POINT]

    paths = []
    total_distance = 0.0
    for i in range(len(waypoints) - 1):
        sx, sy = int(waypoints[i][0]), int(waypoints[i][1])
        gx, gy = int(waypoints[i + 1][0]), int(waypoints[i + 1][1])
        path = astar(grid, (sx, sy), (gx, gy), MAP_WIDTH, MAP_HEIGHT)
        if not path:
            path = [(sx, sy), (gx, gy)]  # Fallback direct line

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

    robot_speed = 0.5  # m/s equivalent in grid units
    pickup_time = 3.0  # seconds per bin
    est_time = (total_distance / robot_speed) + (len(ordered_ids) * pickup_time)

    return SimulationPlanResponse(
        ordered_bin_ids=ordered_ids,
        paths=paths,
        total_distance=round(total_distance, 2),
        estimated_time_sec=round(est_time, 1),
    )
