import json
from typing import Any, Optional
from playwright.async_api import Page, Route, Request


class MockAPI:
    @staticmethod
    async def mock_chatwoot_success(route: Route, request: Request):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "id": 12345}),
        )

    @staticmethod
    async def mock_chatwoot_error(route: Route, request: Request):
        await route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"error": "Internal server error"}),
        )

    @staticmethod
    async def mock_webhook_success(route: Route, request: Request):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"received": True}),
        )

    @staticmethod
    async def mock_webhook_timeout(route: Route, request: Request):
        await route.abort("timedout")

    @staticmethod
    async def mock_bridge_connected(route: Route, request: Request):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "connection_state": "connected",
                    "jid": "1234567890@s.whatsapp.net",
                    "phone": "1234567890",
                    "name": "Test User",
                }
            ),
        )

    @staticmethod
    async def mock_bridge_pending_qr(route: Route, request: Request):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "connection_state": "pending_qr",
                    "qr": "data:image/png;base64,testqrdata",
                }
            ),
        )

    @staticmethod
    async def mock_bridge_disconnected(route: Route, request: Request):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"connection_state": "disconnected"}),
        )


async def setup_mock_routes(page: Page, routes: Optional[dict[str, Any]] = None):
    default_routes = {
        "**/api/chatwoot/**": MockAPI.mock_chatwoot_success,
        "**/webhook**": MockAPI.mock_webhook_success,
        "**/api/status**": MockAPI.mock_bridge_connected,
    }

    routes = routes or default_routes

    for pattern, handler in routes.items():
        await page.route(pattern, handler)

    return routes


async def teardown_mock_routes(page: Page, routes: dict[str, Any]):
    for pattern in routes:
        await page.unroute(pattern)


class WebSocketMock:
    def __init__(self):
        self.messages: list[dict] = []
        self._connected = False

    def send_json(self, data: dict):
        self.messages.append(data)

    def connect(self):
        self._connected = True

    def close(self):
        self._connected = False

    def get_tenant_state_event(self, tenant_hash: str, state: str) -> dict:
        return {
            "type": "tenant_state_changed",
            "data": {
                "tenant_hash": tenant_hash,
                "state": state,
                "timestamp": "2024-01-01T00:00:00Z",
            },
        }

    def get_new_message_event(self, tenant_hash: str, text: str) -> dict:
        return {
            "type": "new_message",
            "data": {
                "tenant_hash": tenant_hash,
                "message": {
                    "id": "msg_123",
                    "text": text,
                    "from": "1234567890@s.whatsapp.net",
                    "push_name": "Test Contact",
                },
            },
        }

    def get_qr_event(self, tenant_hash: str, qr_data: str) -> dict:
        return {
            "type": "qr_generated",
            "data": {"tenant_hash": tenant_hash, "qr": qr_data},
        }

    def get_webhook_attempt_event(self, success: bool, url: str) -> dict:
        return {
            "type": "webhook_attempt",
            "data": {
                "url": url,
                "success": success,
                "status_code": 200 if success else 500,
                "latency_ms": 150,
            },
        }

    def get_security_event(self, event_type: str, ip: str) -> dict:
        return {
            "type": "security_event",
            "data": {"event": event_type, "ip": ip, "reason": "failed_auth"},
        }
