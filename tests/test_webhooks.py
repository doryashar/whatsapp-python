import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import Response, ASGITransport, AsyncClient

from src.webhooks import WebhookSender


@pytest.fixture
def webhook_sender():
    return WebhookSender(
        urls=["https://example.com/webhook"],
        secret="test-secret",
        timeout=5,
        max_retries=2,
    )


class TestWebhookSender:
    def test_urls_property(self, webhook_sender):
        assert webhook_sender.urls == ["https://example.com/webhook"]

    def test_add_url(self, webhook_sender):
        webhook_sender.add_url("https://another.com/webhook")
        assert "https://another.com/webhook" in webhook_sender.urls

    def test_add_duplicate_url(self, webhook_sender):
        initial_count = len(webhook_sender.urls)
        webhook_sender.add_url("https://example.com/webhook")
        assert len(webhook_sender.urls) == initial_count

    def test_remove_url(self, webhook_sender):
        webhook_sender.add_url("https://temp.com/webhook")
        result = webhook_sender.remove_url("https://temp.com/webhook")
        assert result is True
        assert "https://temp.com/webhook" not in webhook_sender.urls

    def test_remove_nonexistent_url(self, webhook_sender):
        result = webhook_sender.remove_url("https://nonexistent.com/webhook")
        assert result is False

    def test_sign_payload(self, webhook_sender):
        payload = '{"test":"data"}'
        signature = webhook_sender._sign_payload(payload)
        expected = hmac.new(
            b"test-secret",
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == f"sha256={expected}"

    def test_sign_payload_no_secret(self):
        sender = WebhookSender(secret="")
        signature = sender._sign_payload('{"test":"data"}')
        assert signature == ""

    @pytest.mark.asyncio
    async def test_send_success(self, webhook_sender):
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            results = await webhook_sender.send("message", {"text": "hello"})

            assert results["https://example.com/webhook"].success is True

    @pytest.mark.asyncio
    async def test_send_failure_retries(self, webhook_sender):
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            results = await webhook_sender.send("message", {"text": "hello"})

            assert results["https://example.com/webhook"].success is False
            assert mock_instance.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_no_urls(self):
        sender = WebhookSender(urls=[])
        results = await sender.send("message", {"text": "hello"})
        assert results == {}

    @pytest.mark.asyncio
    async def test_send_includes_signature(self, webhook_sender):
        captured_headers = {}

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200

        async def capture_post(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = capture_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            await webhook_sender.send("message", {"text": "hello"})

            assert "X-Webhook-Signature" in captured_headers
            assert captured_headers["X-Webhook-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_send_payload_format(self, webhook_sender):
        captured_content = {}

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200

        async def capture_post(*args, **kwargs):
            captured_content["content"] = kwargs.get("content")
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = capture_post
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            await webhook_sender.send("message", {"text": "hello"})

            payload = json.loads(captured_content["content"])
            assert payload["type"] == "message"
            assert payload["data"] == {"text": "hello"}
            assert "timestamp" in payload


@pytest.fixture
async def setup_tenant():
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("test_tenant")
    yield {"tenant": tenant, "api_key": api_key}
    await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_webhook_routes(setup_tenant):
    from src.main import app
    from src.tenant import tenant_manager

    api_key = setup_tenant["api_key"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/webhooks", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert "urls" in data

        response = await client.post(
            "/api/webhooks",
            json={"url": "https://test.com/hook"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "added"

        response = await client.delete(
            "/api/webhooks",
            params={"url": "https://test.com/hook"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "removed"


@pytest.mark.asyncio
async def test_webhook_add_invalid_url(setup_tenant):
    from src.main import app

    api_key = setup_tenant["api_key"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/webhooks",
            json={"url": "ftp://invalid.com"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_remove_not_found(setup_tenant):
    from src.main import app

    api_key = setup_tenant["api_key"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(
            "/api/webhooks",
            params={"url": "https://nonexistent.com/hook"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_without_api_key():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_api_key():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status", headers={"X-API-Key": "invalid_key"})
        assert response.status_code == 401
