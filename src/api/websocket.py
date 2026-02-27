import asyncio
import json
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect
from ..bridge import bridge
from ..store.messages import message_store, InboundMessage
from ..webhooks import webhook_sender


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, data: dict[str, Any]):
        message = json.dumps({"type": event_type, "data": data})
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


def handle_bridge_event(event_type: str, params: dict[str, Any]):
    if event_type == "message":
        msg = InboundMessage(
            id=params["id"],
            from_jid=params["from"],
            chat_jid=params["chat_jid"],
            is_group=params.get("is_group", False),
            push_name=params.get("push_name"),
            text=params.get("text", ""),
            msg_type=params.get("type", "text"),
            timestamp=params.get("timestamp", 0),
        )
        message_store.add(msg)

    asyncio.create_task(manager.broadcast(event_type, params))
    asyncio.create_task(webhook_sender.send(event_type, params))


async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
