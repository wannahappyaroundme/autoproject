"""시제품 테스트용 Webots ↔ 웹 실시간 연동 라우터.

Webots 컨트롤러가 상태를 POST하면 WebSocket으로 웹 클라이언트에 브로드캐스트.
시제품: 로봇 2대, 쓰레기통 4개, 30×20 소형 맵.
"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from websocket_manager import manager

router = APIRouter(prefix="/api/webots-prototype", tags=["webots-prototype"])

# 시제품 Webots 로봇 상태 (메모리 저장)
_proto_robots: dict[int, dict] = {}


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


@router.post("/reset")
async def webots_prototype_reset():
    """Webots 상태 초기화."""
    _proto_robots.clear()
    return {"ok": True}
