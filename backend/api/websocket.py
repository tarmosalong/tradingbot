from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.logger import get_logger

logger = get_logger("websocket")

ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket connected", total=len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info("WebSocket disconnected", total=len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected clients."""
        data = json.dumps(message)
        disconnected: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for ws in disconnected:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
