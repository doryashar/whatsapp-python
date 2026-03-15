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


class TestSendStatusRequestValidation:
    def test_valid_with_all_contacts(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="text",
            content="Hello status",
            all_contacts=True,
        )
        assert req.all_contacts is True
        assert req.status_jid_list is None

    def test_valid_with_status_jid_list(self):
        from src.models.group import SendStatusRequest

        req = SendStatusRequest(
            type="text",
            content="Hello status",
            status_jid_list=["1234567890@s.whatsapp.net"],
        )
        assert req.status_jid_list == ["1234567890@s.whatsapp.net"]
        assert req.all_contacts is False

    def test_reject_both_all_contacts_and_jid_list(self):
        from src.models.group import SendStatusRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SendStatusRequest(
                type="text",
                content="Hello status",
                all_contacts=True,
                status_jid_list=["1234567890@s.whatsapp.net"],
            )
        assert "Cannot specify both" in str(exc_info.value)

    def test_reject_neither_all_contacts_nor_jid_list(self):
        from src.models.group import SendStatusRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SendStatusRequest(
                type="text",
                content="Hello status",
            )
        assert "Must specify either" in str(exc_info.value)

    def test_valid_type_values(self):
        from src.models.group import SendStatusRequest

        for status_type in ["text", "image", "video"]:
            req = SendStatusRequest(
                type=status_type,
                content="test",
                all_contacts=True,
            )
            assert req.type == status_type

    def test_reject_invalid_type(self):
        from src.models.group import SendStatusRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SendStatusRequest(
                type="audio",
                content="test",
                all_contacts=True,
            )
