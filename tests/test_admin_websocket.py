import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import json

ADMIN_PASSWORD = "test-admin-password-123"

# Skip WebSocket tests that use websocket_connect which is not available in httpx.AsyncClient
SKIP_WEBSOCKET_TESTS = pytest.mark.skip(
    reason="httpx.AsyncClient does not support websocket_connect. These tests need to be rewritten using proper WebSocket testing tools."
)


@pytest.fixture(autouse=True)
def setup_admin_password(monkeypatch):
    from src import config

    monkeypatch.setattr(config.settings, "admin_password", ADMIN_PASSWORD)
    monkeypatch.setattr(config.settings, "debug", True)
    yield
    monkeypatch.setattr(config.settings, "admin_password", None)
    monkeypatch.setattr(config.settings, "debug", False)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.list_messages = AsyncMock(return_value=([], 0))
    db.get_recent_chats = AsyncMock(return_value=[])
    db.get_webhook_stats = AsyncMock(
        return_value={"total": 0, "success_count": 0, "fail_count": 0}
    )
    db.create_admin_session = AsyncMock(return_value="test-session-id")
    db.get_admin_session = AsyncMock(
        return_value={
            "id": "test-session-id",
            "expires_at": "2099-01-01",
            "user_agent": "test",
            "ip_address": "127.0.0.1",
        }
    )
    db.update_admin_session_expiry = AsyncMock(return_value=None)
    return db


@pytest.fixture
async def setup_tenant_manager(mock_db, monkeypatch):
    from src.tenant import tenant_manager
    from src.store.database import Database

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()

    tenant_manager._db = mock_db
    tenant_manager._tenants.clear()

    yield tenant_manager

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_admin_ws_requires_session():
    """Test that WebSocket connection requires valid session"""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Try to connect without session_id
        with pytest.raises(Exception):
            async with client.websocket_connect("/admin/ws") as websocket:
                pass


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_admin_ws_requires_valid_session(setup_tenant_manager):
    """Test that WebSocket connection validates session"""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Try to connect with invalid session_id
        with pytest.raises(Exception):
            async with client.websocket_connect(
                "/admin/ws?session_id=invalid-session"
            ) as websocket:
                pass


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_admin_ws_connects_with_valid_session(setup_tenant_manager):
    """Test successful WebSocket connection with valid session"""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login first
        login_response = await client.post(
            "/admin/login", data={"password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 302

        # Get session ID
        session_response = await client.get("/admin/api/session-id")
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Send ping
            await websocket.send_json({"type": "ping"})

            # Should receive pong
            response = await websocket.receive_json()
            assert response["type"] == "pong"


@pytest.mark.asyncio
async def test_admin_ws_manager_broadcast():
    """Test AdminConnectionManager broadcast functionality"""
    from src.admin.websocket import AdminConnectionManager

    manager = AdminConnectionManager()

    # Create mock WebSocket connections
    mock_ws1 = MagicMock()
    mock_ws1.send_text = AsyncMock()
    mock_ws1.accept = AsyncMock()

    mock_ws2 = MagicMock()
    mock_ws2.send_text = AsyncMock()
    mock_ws2.accept = AsyncMock()

    # Connect both
    await manager.connect(mock_ws1, "session1")
    await manager.connect(mock_ws2, "session2")

    assert manager.get_connection_count() == 2

    # Broadcast event
    await manager.broadcast("test_event", {"message": "Hello", "count": 42})

    # Both connections should receive the message
    assert mock_ws1.send_text.called
    assert mock_ws2.send_text.called

    # Check message content
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

    # Broadcast should handle exception and disconnect
    await manager.broadcast("test_event", {"data": "test"})

    # Connection should be removed after failed send
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


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_tenant_state_change_broadcast(setup_tenant_manager):
    """Test that tenant state changes are broadcast via WebSocket"""
    from src.main import app, admin_ws_manager
    from src.admin.websocket import AdminConnectionManager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login and get session
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
        session_response = await client.get("/admin/api/session-id")
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Trigger tenant state change (this would normally happen via bridge event)
            # For testing, we'll broadcast directly
            await admin_ws_manager.broadcast(
                "tenant_state_changed",
                {
                    "tenant_hash": "test-hash",
                    "tenant_name": "Test Tenant",
                    "event": "connected",
                    "params": {"jid": "test@s.whatsapp.net"},
                },
            )

            # Receive the broadcast
            message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
            assert message["type"] == "tenant_state_changed"
            assert message["data"]["tenant_name"] == "Test Tenant"
            assert message["data"]["event"] == "connected"


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_new_message_broadcast(setup_tenant_manager):
    """Test that new messages are broadcast via WebSocket"""
    from src.main import app, admin_ws_manager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login and get session
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
        session_response = await client.get("/admin/api/session-id")
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Broadcast a new message
            await admin_ws_manager.broadcast(
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

            # Receive the broadcast
            message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
            assert message["type"] == "new_message"
            assert message["data"]["tenant_name"] == "Test Tenant"
            assert message["data"]["message"]["text"] == "Hello world"


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_webhook_attempt_broadcast(setup_tenant_manager):
    """Test that webhook attempts are broadcast via WebSocket"""
    from src.main import app, admin_ws_manager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login and get session
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
        session_response = await client.get("/admin/api/session-id")
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Broadcast a webhook attempt
            await admin_ws_manager.broadcast(
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

            # Receive the broadcast
            message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
            assert message["type"] == "webhook_attempt"
            assert message["data"]["success"] == False
            assert message["data"]["status_code"] == 500


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_security_event_broadcast(setup_tenant_manager):
    """Test that security events are broadcast via WebSocket"""
    from src.main import app, admin_ws_manager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login and get session
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
        session_response = await client.get("/admin/api/session-id")
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Broadcast a security event
            await admin_ws_manager.broadcast(
                "security_event",
                {
                    "event": "ip_blocked",
                    "ip": "192.168.1.100",
                    "reason": "failed_auth:5",
                },
            )

            # Receive the broadcast
            message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
            assert message["type"] == "security_event"
            assert message["data"]["event"] == "ip_blocked"
            assert message["data"]["ip"] == "192.168.1.100"


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_multiple_clients_receive_broadcast(setup_tenant_manager):
    """Test that multiple WebSocket clients all receive broadcasts"""
    from src.main import app, admin_ws_manager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client1:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client2:
            # Login both clients
            await client1.post("/admin/login", data={"password": ADMIN_PASSWORD})
            session1 = (await client1.get("/admin/api/session-id")).json()["session_id"]

            await client2.post("/admin/login", data={"password": ADMIN_PASSWORD})
            session2 = (await client2.get("/admin/api/session-id")).json()["session_id"]

            # Connect both to WebSocket
            async with client1.websocket_connect(
                f"/admin/ws?session_id={session1}"
            ) as ws1:
                async with client2.websocket_connect(
                    f"/admin/ws?session_id={session2}"
                ) as ws2:
                    # Broadcast an event
                    await admin_ws_manager.broadcast(
                        "test_event", {"data": "broadcast test"}
                    )

                    # Both should receive
                    msg1 = await asyncio.wait_for(ws1.receive_json(), timeout=2.0)
                    msg2 = await asyncio.wait_for(ws2.receive_json(), timeout=2.0)

                    assert msg1["type"] == "test_event"
                    assert msg2["type"] == "test_event"
                    assert msg1["data"]["data"] == "broadcast test"
                    assert msg2["data"]["data"] == "broadcast test"


@pytest.mark.asyncio
@SKIP_WEBSOCKET_TESTS
async def test_qr_code_broadcast(setup_tenant_manager):
    """Test that QR codes are broadcast via WebSocket when generated"""
    from src.main import app, admin_ws_manager

    # Clear any existing connections
    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login and get session
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
        session_response = await client.get("/admin/api/session-id")
        session_id = session_response.json()["session_id"]

        # Connect to WebSocket
        async with client.websocket_connect(
            f"/admin/ws?session_id={session_id}"
        ) as websocket:
            # Broadcast a QR code event (simulating what happens in main.py)
            await admin_ws_manager.broadcast(
                "qr_generated",
                {
                    "tenant_hash": "test-hash",
                    "tenant_name": "Test Tenant",
                    "qr": "qr-code-data",
                    "qr_data_url": "data:image/png;base64,test",
                },
            )

            # Receive the broadcast
            message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
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
async def test_websockets_api_endpoint(setup_tenant_manager):
    """Test /admin/api/websockets API endpoint"""
    from src.main import app, admin_ws_manager
    from src.admin.websocket import AdminConnectionManager

    await admin_ws_manager.close_all()

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.accept = AsyncMock()

    await admin_ws_manager.connect(mock_ws, "test-session-12345678")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.get("/admin/api/websockets")
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


@pytest.mark.asyncio
async def test_websockets_fragment_endpoint(setup_tenant_manager):
    """Test /admin/fragments/websockets fragment endpoint"""
    from src.main import app, admin_ws_manager

    await admin_ws_manager.close_all()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.get("/admin/fragments/websockets")
        assert response.status_code == 200
        html = response.text
        assert "no active" in html.lower() or "session" in html.lower()
