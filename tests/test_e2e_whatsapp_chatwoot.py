import pytest
import os
import hashlib
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock


E2E_TEST_PHONE = os.environ.get("E2E_TEST_PHONE", "1234567890")
E2E_API_KEY = os.environ.get("E2E_API_KEY", "")
if not E2E_API_KEY:
    pytest.skip("E2E_API_KEY environment variable not set", allow_module_level=True)


def get_tenant_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


@pytest.fixture
def tenant_hash():
    return get_tenant_hash(E2E_API_KEY)


@pytest.fixture
def tenant_hash_short():
    return get_tenant_hash(E2E_API_KEY)[:16]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_send_message_to_test_phone():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/send",
            headers={"X-API-Key": E2E_API_KEY},
            json={"to": E2E_TEST_PHONE, "text": "E2E test message from API"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message_id" in data
        assert E2E_TEST_PHONE in data.get("to", "")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_whatsapp_tenant_is_connected():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/status",
            headers={"X-API-Key": E2E_API_KEY},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("connection_state") == "connected"
        assert "self_info" in data
        assert "jid" in data["self_info"]


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_chatwoot_webhook_send_message(tenant_hash):
    from src.main import app

    webhook_url = f"/webhooks/chatwoot/{tenant_hash}/outgoing"

    payload = {
        "event": "message_created",
        "message_type": "outgoing",
        "message": {
            "id": 99999,
            "content": "E2E test message from Chatwoot webhook",
            "message_type": "outgoing",
            "private": False,
        },
        "conversation": {
            "id": 1,
            "meta": {"sender": {"phone_number": f"+{E2E_TEST_PHONE}"}},
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            webhook_url,
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "sent"
        assert E2E_TEST_PHONE in data.get("to", "")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_chatwoot_webhook_with_short_hash_fails(tenant_hash_short):
    from src.main import app

    webhook_url = f"/webhooks/chatwoot/{tenant_hash_short}/outgoing"

    payload = {
        "event": "message_created",
        "message_type": "outgoing",
        "message": {
            "id": 99998,
            "content": "This should work with short hash fix",
            "message_type": "outgoing",
            "private": False,
        },
        "conversation": {
            "id": 1,
            "meta": {"sender": {"phone_number": f"+{E2E_TEST_PHONE}"}},
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            webhook_url,
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "sent"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_e2e_flow():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        status_response = await client.get(
            "/api/status",
            headers={"X-API-Key": E2E_API_KEY},
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data.get("connection_state") == "connected"

        send_response = await client.post(
            "/api/send",
            headers={"X-API-Key": E2E_API_KEY},
            json={"to": E2E_TEST_PHONE, "text": "E2E full flow - direct API"},
        )
        assert send_response.status_code == 200
        send_data = send_response.json()
        assert "message_id" in send_data

        tenant_hash = get_tenant_hash(E2E_API_KEY)
        webhook_response = await client.post(
            f"/webhooks/chatwoot/{tenant_hash}/outgoing",
            json={
                "event": "message_created",
                "message_type": "outgoing",
                "message": {
                    "id": 99997,
                    "content": "E2E full flow - Chatwoot webhook",
                    "message_type": "outgoing",
                    "private": False,
                },
                "conversation": {
                    "id": 1,
                    "meta": {"sender": {"phone_number": f"+{E2E_TEST_PHONE}"}},
                },
            },
        )
        assert webhook_response.status_code == 200
        webhook_data = webhook_response.json()
        assert webhook_data.get("status") == "sent"
