import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_tenant_manager():
    from src.tenant import TenantManager

    manager = TenantManager()
    return manager


@pytest.mark.asyncio
async def test_health_check():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_status_unauthorized():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unauthorized():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/login")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_message_unauthorized():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/send",
            json={"to": "+1234567890", "text": "Hello!"},
        )
        assert response.status_code == 401
