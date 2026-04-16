"""시제품 테스트용 Webots ↔ 웹 실시간 연동 라우터.

Webots 컨트롤러가 상태를 POST하면 WebSocket으로 웹 클라이언트에 브로드캐스트.
시제품: 로봇 2대, 쓰레기통 4개, 30×20 소형 맵.
"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from websocket_manager import manager

router = APIRouter(prefix="/api/webots-prototype", tags=["webots-prototype"])

# 시제품 Webots 로봇 상태 (메모리 저장)
_proto_robots: dict[int, dict] = {}
# 동적 장애물 상태 (웹에서 전송, Webots에서 읽기)
_proto_obstacles: list[dict] = []


@router.post("/state")
async def webots_prototype_state(request: Request):
    """Webots 시제품 컨트롤러에서 200ms마다 호출. 상태 수신 + WebSocket 브로드캐스트."""
    data = await request.json()
    robot_id = data.get("robot_id", 0)
    _proto_robots[robot_id] = data
    await manager.broadcast("webots-prototype-live", data)
    return {"ok": True}


@router.get("/robots")
async def webots_prototype_robots():
    """현재 Webots 시제품 로봇 2대 상태 조회."""
    return {"robots": list(_proto_robots.values())}


@router.post("/obstacles")
async def webots_prototype_obstacles_update(request: Request):
    """웹 시뮬레이션에서 장애물 위치를 전송. Webots가 읽어감."""
    global _proto_obstacles
    data = await request.json()
    _proto_obstacles = data.get("obstacles", [])
    return {"ok": True}


@router.get("/obstacles")
async def webots_prototype_obstacles_get():
    """Webots 컨트롤러가 현재 장애물 위치를 조회."""
    return {"obstacles": _proto_obstacles}


@router.post("/reset")
async def webots_prototype_reset():
    """Webots 상태 초기화."""
    global _proto_obstacles
    _proto_robots.clear()
    _proto_obstacles = []
    return {"ok": True}
