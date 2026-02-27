import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_bridge():
    with patch("src.api.routes.bridge") as mock:
        mock.get_status = AsyncMock(
            return_value={
                "connection_state": "disconnected",
                "self": None,
                "has_qr": False,
            }
        )
        mock.login = AsyncMock(
            return_value={
                "status": "qr_ready",
                "qr": "test-qr-data",
                "qr_data_url": "data:image/png;base64,test",
            }
        )
        mock.logout = AsyncMock(return_value={"status": "logged_out"})
        mock.send_message = AsyncMock(
            return_value={
                "message_id": "msg123",
                "to": "1234567890@s.whatsapp.net",
            }
        )
        mock.send_reaction = AsyncMock(
            return_value={
                "status": "reacted",
                "chat": "1234567890@s.whatsapp.net",
            }
        )
        yield mock


@pytest.mark.asyncio
async def test_health_check():
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_status(mock_bridge):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connection_state"] == "disconnected"


@pytest.mark.asyncio
async def test_login(mock_bridge):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/login")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "qr_ready"
        assert data["qr"] == "test-qr-data"


@pytest.mark.asyncio
async def test_send_message(mock_bridge):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/send",
            json={"to": "+1234567890", "text": "Hello!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == "msg123"
