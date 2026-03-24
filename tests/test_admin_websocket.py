import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio
import json
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from tests.conftest import ADMIN_PASSWORD


@pytest.fixture
def ws_client():
    from src.main import app

    client = TestClient(app)
    yield client
    client.close()


def test_admin_ws_requires_session(ws_client):
    """Test that WebSocket connection requires valid session"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/admin/ws") as websocket:
            websocket.receive()
    assert exc_info.value.code == 1008
    assert "Session ID required" in exc_info.value.reason


def test_admin_ws_requires_valid_session(ws_client, setup_tenant_manager):
    """Test that WebSocket connection validates session"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(
            "/admin/ws?session_id=invalid-session"
        ) as websocket:
            websocket.receive()
    assert exc_info.value.code == 1008
    assert "Invalid session" in exc_info.value.reason


def test_admin_ws_connects_with_valid_session(ws_client, setup_tenant_manager):
    """Test successful WebSocket connection with valid session"""
    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        websocket.send_json({"type": "ping"})
        response = websocket.receive_json()
        assert response["type"] == "pong"


@pytest.mark.asyncio
async def test_admin_ws_manager_broadcast():
    """Test AdminConnectionManager broadcast functionality"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    mock_ws1 = MagicMock()
    mock_ws1.send_text = AsyncMock()
    mock_ws1.accept = AsyncMock()

    mock_ws2 = MagicMock()
    mock_ws2.send_text = AsyncMock()
    mock_ws2.accept = AsyncMock()

    await manager.connect(mock_ws1, "session1")
    await manager.connect(mock_ws2, "session2")

    assert manager.get_connection_count() == 2

    await manager.broadcast("test_event", {"message": "Hello", "count": 42})

    assert mock_ws1.send_text.called
    assert mock_ws2.send_text.called

    call_args = mock_ws1.send_text.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "test_event"
    assert message["data"]["message"] == "Hello"
    assert message["data"]["count"] == 42
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_admin_ws_manager_disconnect():
    """Test AdminConnectionManager disconnect functionality"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.accept = AsyncMock()

    await manager.connect(mock_ws, "session1")
    assert manager.get_connection_count() == 1

    await manager.disconnect(mock_ws)
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_admin_ws_manager_handles_failed_send():
    """Test that manager handles failed send operations gracefully"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock(side_effect=Exception("Connection lost"))

    await manager.connect(mock_ws, "session1")
    assert manager.get_connection_count() == 1

    await manager.broadcast("test_event", {"data": "test"})

    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_admin_ws_manager_close_all():
    """Test closing all connections"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    mock_ws1 = MagicMock()
    mock_ws1.accept = AsyncMock()
    mock_ws1.close = AsyncMock()

    mock_ws2 = MagicMock()
    mock_ws2.accept = AsyncMock()
    mock_ws2.close = AsyncMock()

    await manager.connect(mock_ws1, "session1")
    await manager.connect(mock_ws2, "session2")
    assert manager.get_connection_count() == 2

    await manager.close_all()
    assert manager.get_connection_count() == 0


def test_tenant_state_change_broadcast(ws_client, setup_tenant_manager):
    """Test that tenant state changes are broadcast via WebSocket"""
    from src.main import admin_ws_manager

    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        asyncio.get_event_loop().run_until_complete(
            admin_ws_manager.broadcast(
                "tenant_state_changed",
                {
                    "tenant_hash": "test-hash",
                    "tenant_name": "Test Tenant",
                    "event": "connected",
                    "params": {"jid": "test@s.whatsapp.net"},
                },
            )
        )

        message = websocket.receive_json()
        assert message["type"] == "tenant_state_changed"
        assert message["data"]["tenant_name"] == "Test Tenant"
        assert message["data"]["event"] == "connected"


def test_new_message_broadcast(ws_client, setup_tenant_manager):
    """Test that new messages are broadcast via WebSocket"""
    from src.main import admin_ws_manager

    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        asyncio.get_event_loop().run_until_complete(
            admin_ws_manager.broadcast(
                "new_message",
                {
                    "tenant_hash": "test-hash",
                    "tenant_name": "Test Tenant",
                    "message": {
                        "id": "msg123",
                        "from": "sender@s.whatsapp.net",
                        "text": "Hello world",
                        "timestamp": 1234567890,
                    },
                },
            )
        )

        message = websocket.receive_json()
        assert message["type"] == "new_message"
        assert message["data"]["tenant_name"] == "Test Tenant"
        assert message["data"]["message"]["text"] == "Hello world"


def test_webhook_attempt_broadcast(ws_client, setup_tenant_manager):
    """Test that webhook attempts are broadcast via WebSocket"""
    from src.main import admin_ws_manager

    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        asyncio.get_event_loop().run_until_complete(
            admin_ws_manager.broadcast(
                "webhook_attempt",
                {
                    "tenant_hash": "test-hash",
                    "url": "https://example.com/webhook",
                    "event_type": "message",
                    "success": False,
                    "status_code": 500,
                    "error_message": "Internal Server Error",
                },
            )
        )

        message = websocket.receive_json()
        assert message["type"] == "webhook_attempt"
        assert message["data"]["success"] == False
        assert message["data"]["status_code"] == 500


def test_security_event_broadcast(ws_client, setup_tenant_manager):
    """Test that security events are broadcast via WebSocket"""
    from src.main import admin_ws_manager

    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        asyncio.get_event_loop().run_until_complete(
            admin_ws_manager.broadcast(
                "security_event",
                {
                    "event": "ip_blocked",
                    "ip": "192.168.1.100",
                    "reason": "failed_auth:5",
                },
            )
        )

        message = websocket.receive_json()
        assert message["type"] == "security_event"
        assert message["data"]["event"] == "ip_blocked"
        assert message["data"]["ip"] == "192.168.1.100"


def test_multiple_clients_receive_broadcast(ws_client, setup_tenant_manager):
    """Test that multiple WebSocket clients all receive broadcasts"""
    from src.main import app, admin_ws_manager

    client2 = TestClient(app)

    login_response1 = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response1.status_code == 302
    session1 = ws_client.get("/admin/api/session-id").json()["session_id"]

    login_response2 = client2.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response2.status_code == 302
    session2 = client2.get("/admin/api/session-id").json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session1}") as ws1:
        with client2.websocket_connect(f"/admin/ws?session_id={session2}") as ws2:
            asyncio.get_event_loop().run_until_complete(
                admin_ws_manager.broadcast("test_event", {"data": "broadcast test"})
            )

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["type"] == "test_event"
            assert msg2["type"] == "test_event"
            assert msg1["data"]["data"] == "broadcast test"
            assert msg2["data"]["data"] == "broadcast test"

    client2.close()


def test_qr_code_broadcast(ws_client, setup_tenant_manager):
    """Test that QR codes are broadcast via WebSocket when generated"""
    from src.main import admin_ws_manager

    login_response = ws_client.post(
        "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
    )
    assert login_response.status_code == 302

    session_response = ws_client.get("/admin/api/session-id")
    session_id = session_response.json()["session_id"]

    with ws_client.websocket_connect(f"/admin/ws?session_id={session_id}") as websocket:
        asyncio.get_event_loop().run_until_complete(
            admin_ws_manager.broadcast(
                "qr_generated",
                {
                    "tenant_hash": "test-hash",
                    "tenant_name": "Test Tenant",
                    "qr": "qr-code-data",
                    "qr_data_url": "data:image/png;base64,test",
                },
            )
        )

        message = websocket.receive_json()
        assert message["type"] == "qr_generated"
        assert message["data"]["tenant_name"] == "Test Tenant"
        assert message["data"]["qr"] == "qr-code-data"
        assert message["data"]["qr_data_url"] == "data:image/png;base64,test"


@pytest.mark.asyncio
async def test_get_connections_info():
    """Test AdminConnectionManager get_connections_info method"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    mock_ws1 = MagicMock()
    mock_ws1.send_text = AsyncMock()
    mock_ws1.accept = AsyncMock()

    mock_ws2 = MagicMock()
    mock_ws2.send_text = AsyncMock()
    mock_ws2.accept = AsyncMock()

    await manager.connect(mock_ws1, "session-id-12345678")
    await manager.connect(mock_ws2, "short-id")

    connections = manager.get_connections_info()
    assert len(connections) == 2

    session_ids = [c["session_id"] for c in connections]
    assert "session-id-12345..." in session_ids
    assert "short-id" in session_ids

    for conn in connections:
        assert "session_id" in conn
        assert "connected_at" in conn

    await manager.disconnect(mock_ws1)
    await manager.disconnect(mock_ws2)
    assert len(manager.get_connections_info()) == 0


@pytest.mark.asyncio
async def test_websockets_api_endpoint(ws_client, setup_tenant_manager):
    """Test /admin/api/websockets API endpoint"""
    from src.main import admin_ws_manager

    await admin_ws_manager.close_all()

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.accept = AsyncMock()

    await admin_ws_manager.connect(mock_ws, "test-session-12345678")

    ws_client.post("/admin/login", data={"password": ADMIN_PASSWORD})

    response = ws_client.get("/admin/api/websockets")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "connections" in data
    assert data["count"] >= 1
    assert len(data["connections"]) >= 1

    for conn in data["connections"]:
        assert "session_id" in conn
        assert "connected_at" in conn

    await admin_ws_manager.close_all()


def test_websockets_fragment_endpoint(ws_client, setup_tenant_manager):
    """Test /admin/fragments/websockets fragment endpoint"""
    from src.main import admin_ws_manager

    asyncio.get_event_loop().run_until_complete(admin_ws_manager.close_all())

    ws_client.post("/admin/login", data={"password": ADMIN_PASSWORD})

    response = ws_client.get("/admin/fragments/websockets")
    assert response.status_code == 200
    html = response.text
    assert "no active" in html.lower() or "session" in html.lower()
