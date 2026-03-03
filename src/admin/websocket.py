import asyncio
import json
from typing import Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

from ..telemetry import get_logger

logger = get_logger("whatsapp.admin.websocket")


class AdminConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._connection_sessions: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
        logger.info("AdminConnectionManager initialized")

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
            self._connection_sessions[websocket] = session_id
        logger.info(
            f"Admin WebSocket connected: session={session_id[:16]}..., total={len(self._connections)}"
        )

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
                session_id = self._connection_sessions.pop(websocket, "unknown")
                logger.info(
                    f"Admin WebSocket disconnected: session={session_id[:16] if len(session_id) >= 16 else session_id}..., remaining={len(self._connections)}"
                )

    async def broadcast(self, event_type: str, data: dict[str, Any]):
        if not self._connections:
            return

        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        disconnected = []
        async with self._lock:
            connections_copy = self._connections[:]

        for connection in connections_copy:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send to connection: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            await self.disconnect(conn)

        logger.debug(
            f"Broadcast event '{event_type}' to {len(connections_copy) - len(disconnected)} connections"
        )

    async def send_to_connection(
        self, websocket: WebSocket, event_type: str, data: dict[str, Any]
    ):
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.debug(f"Failed to send to connection: {e}")
            await self.disconnect(websocket)

    def get_connection_count(self) -> int:
        return len(self._connections)

    async def close_all(self):
        async with self._lock:
            for connection in self._connections[:]:
                try:
                    await connection.close()
                except Exception:
                    pass
            self._connections.clear()
            self._connection_sessions.clear()
        logger.info("All admin WebSocket connections closed")


admin_ws_manager = AdminConnectionManager()
