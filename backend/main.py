import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import CORS_ORIGINS
from database import init_db, get_db
from models import Mission, MissionBin, Bin, Robot
from websocket_manager import manager
from services.simulation_engine import SimulationEngine

from routers import auth, areas, bins, missions, robots, simulation, vision


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="자율주행 쓰레기통 수거 로봇 — 테스트 플랫폼",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(areas.router)
app.include_router(bins.router)
app.include_router(missions.router)
app.include_router(robots.router)
app.include_router(simulation.router)
app.include_router(vision.router)

# Active simulations
_simulations: dict[int, SimulationEngine] = {}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "robot-test-platform"}


# --- WebSocket: Simulation ---
@app.websocket("/ws/simulation/{mission_id}")
async def ws_simulation(websocket: WebSocket, mission_id: int):
    channel = f"sim-{mission_id}"
    await manager.connect(channel, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("action") == "start":
                # Get mission plan from simulation router
                from routers.simulation import get_default_map, COLLECTION_POINT, MAP_WIDTH, MAP_HEIGHT
                from services.pathfinding import astar
                from services.mission_planner import optimize_visit_order

                async for db in get_db():
                    result = await db.execute(
                        select(Mission).options(
                            selectinload(Mission.mission_bins).selectinload(MissionBin.bin)
                        ).where(Mission.id == mission_id)
                    )
                    mission = result.scalar_one_or_none()
                    if not mission:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Mission not found"}))
                        continue

                    bin_positions = {}
                    bin_ids_ordered = []
                    for mb in sorted(mission.mission_bins, key=lambda x: x.order_index):
                        if mb.bin:
                            bin_positions[mb.bin_id] = (mb.bin.map_x, mb.bin.map_y)
                            bin_ids_ordered.append(mb.bin_id)

                    ordered_ids = optimize_visit_order(COLLECTION_POINT, bin_positions)
                    grid = get_default_map()

                    waypoints = [COLLECTION_POINT] + [bin_positions[bid] for bid in ordered_ids] + [COLLECTION_POINT]
                    paths = []
                    for i in range(len(waypoints) - 1):
                        sx, sy = int(waypoints[i][0]), int(waypoints[i][1])
                        gx, gy = int(waypoints[i + 1][0]), int(waypoints[i + 1][1])
                        path = astar(grid, (sx, sy), (gx, gy), MAP_WIDTH, MAP_HEIGHT)
                        if not path:
                            path = [(sx, sy), (gx, gy)]
                        paths.append([(float(p[0]), float(p[1])) for p in path])

                    # Get robot info for color
                    robot_id = mission.robot_id or 1
                    robot_color = "#ef4444"
                    if mission.robot_id:
                        robot_result = await db.execute(select(Robot).where(Robot.id == mission.robot_id))
                        robot_obj = robot_result.scalar_one_or_none()
                        if robot_obj:
                            robot_color = robot_obj.color or "#ef4444"

                    engine = SimulationEngine(paths, ordered_ids, robot_id=robot_id, robot_color=robot_color)
                    _simulations[mission_id] = engine

                    async def broadcast_fn(data: dict):
                        await manager.broadcast(channel, data)

                    asyncio.create_task(engine.run(broadcast_fn))
                    break

            elif msg.get("action") == "stop":
                if mission_id in _simulations:
                    _simulations[mission_id].stop()
                    del _simulations[mission_id]

    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)
        if mission_id in _simulations:
            _simulations[mission_id].stop()
            del _simulations[mission_id]


# --- WebSocket: Real-time robot positions ---
@app.websocket("/ws/robots")
async def ws_robots(websocket: WebSocket):
    channel = "robots-live"
    await manager.connect(channel, websocket)
    try:
        while True:
            # Client sends ping or request; we respond with all robot positions
            await websocket.receive_text()
            async for db in get_db():
                result = await db.execute(select(Robot))
                robots_data = []
                for r in result.scalars().all():
                    robots_data.append({
                        "id": r.id,
                        "name": r.name,
                        "state": r.state,
                        "battery": r.battery,
                        "x": r.position_x,
                        "y": r.position_y,
                        "color": r.color or "#ef4444",
                        "current_mission_id": r.current_mission_id,
                    })
                break
            await websocket.send_text(json.dumps({"type": "robots_update", "robots": robots_data}))
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


# --- Webots → Web 실시간 연동 ---

# Webots 로봇 상태 임시 저장 (메모리)
_webots_robots: dict[int, dict] = {}


@app.post("/api/webots/state")
async def webots_state_update(request: Request):
    """Webots 컨트롤러에서 200ms마다 호출. 로봇 상태 수신 + WebSocket 브로드캐스트."""
    data = await request.json()
    robot_id = data.get("robot_id", 0)
    _webots_robots[robot_id] = data
    await manager.broadcast("webots-live", data)
    return {"ok": True}


@app.get("/api/webots/robots")
async def webots_robots_state():
    """현재 Webots 로봇 4대 상태 한번에 조회."""
    return {"robots": list(_webots_robots.values())}


@app.websocket("/ws/webots")
async def ws_webots(websocket: WebSocket):
    """Webots 실시간 데이터를 웹 클라이언트에게 스트리밍."""
    channel = "webots-live"
    await manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)
