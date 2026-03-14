"""WebSocket connection manager for real-time updates."""
import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, channel: str, websocket: WebSocket):
        await websocket.accept()
        if channel not in self.active:
            self.active[channel] = []
        self.active[channel].append(websocket)

    def disconnect(self, channel: str, websocket: WebSocket):
        if channel in self.active:
            self.active[channel] = [ws for ws in self.active[channel] if ws != websocket]

    async def broadcast(self, channel: str, data: dict):
        if channel not in self.active:
            return
        dead = []
        for ws in self.active[channel]:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active[channel] = [w for w in self.active[channel] if w != ws]


manager = ConnectionManager()
