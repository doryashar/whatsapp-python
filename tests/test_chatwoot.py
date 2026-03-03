import pytest
from unittest.mock import Mock, AsyncMock, patch
import json

from src.chatwoot import (
    ChatwootConfig,
    ChatwootContact,
    ChatwootConversation,
    ChatwootMessage,
    ChatwootClient,
    ChatwootIntegration,
    ChatwootWebhookHandler,
    ChatwootAPIError,
)


class TestChatwootConfig:
    def test_config_defaults(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.enabled is False
        assert config.sign_messages is True
        assert config.reopen_conversation is True
        assert config.import_contacts is True
        assert config.merge_brazil_contacts is True

    def test_config_custom_values(self):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id="2",
            sign_messages=False,
            reopen_conversation=False,
        )
        assert config.enabled is True
        assert config.inbox_id == "2"
        assert config.sign_messages is False
        assert config.reopen_conversation is False


class TestChatwootContact:
    def test_contact_creation(self):
        contact = ChatwootContact(
            id=1,
            name="John Doe",
            phone_number="+1234567890",
        )
        assert contact.id == 1
        assert contact.name == "John Doe"
        assert contact.phone_number == "+1234567890"


class TestChatwootConversation:
    def test_conversation_creation(self):
        conv = ChatwootConversation(
            id=1,
            account_id=1,
            inbox_id=1,
            contact_id=1,
            status="open",
        )
        assert conv.id == 1
        assert conv.status == "open"


class TestChatwootMessage:
    def test_message_creation(self):
        msg = ChatwootMessage(
            id=1,
            content="Hello",
            conversation_id=1,
            account_id=1,
        )
        assert msg.id == 1
        assert msg.content == "Hello"
        assert msg.message_type == "incoming"


class TestChatwootClient:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id="1",
        )

    def test_normalize_phone(self, config):
        client = ChatwootClient(config)

        assert client._normalize_phone("1234567890") == "+1234567890"
        assert client._normalize_phone("+1234567890") == "+1234567890"
        assert client._normalize_phone("+1 (234) 567-890") == "+1234567890"

    def test_brazil_number_variants(self, config):
        client = ChatwootClient(config)

        variant = client._try_brazil_number_variants("5511987654321")
        assert variant == "+551187654321"

        variant = client._try_brazil_number_variants("551187654321")
        assert variant == "+5511987654321"

        variant = client._try_brazil_number_variants("1234567890")
        assert variant is None


class TestChatwootIntegration:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.chatwoot_config = {
            "enabled": True,
            "url": "https://chatwoot.example.com",
            "token": "test_token",
            "account_id": "1",
            "inbox_id": "1",
        }
        return tenant

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id="1",
        )

    def test_extract_phone(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        phone = integration._extract_phone("1234567890@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = integration._extract_phone("1234567890:12@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = integration._extract_phone("invalid")
        assert phone is None

    @pytest.mark.asyncio
    async def test_handle_message_disabled(self, mock_tenant):
        config = ChatwootConfig(enabled=False, url="", token="", account_id="")
        integration = ChatwootIntegration(config, mock_tenant)

        result = await integration.handle_message({"from": "test@s.whatsapp.net"})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_group_skipped(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        result = await integration.handle_message(
            {
                "from": "test@s.whatsapp.net",
                "is_group": True,
            }
        )
        assert result is False


class TestChatwootWebhookHandler:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        bridge.send_message = AsyncMock(return_value={"status": "sent"})
        return bridge

    def test_verify_signature_valid(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, hmac_token="secret")

        payload = b'{"event": "test"}'
        signature = (
            "sha256="
            + __import__("hmac")
            .new(b"secret", payload, __import__("hashlib").sha256)
            .hexdigest()
        )

        assert handler.verify_signature(payload, signature) is True

    def test_verify_signature_invalid(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, hmac_token="secret")

        payload = b'{"event": "test"}'
        signature = "sha256=invalid"

        assert handler.verify_signature(payload, signature) is False

    def test_verify_signature_no_token(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge)

        assert handler.verify_signature(b"{}", "any") is True

    @pytest.mark.asyncio
    async def test_handle_webhook_ignores_non_outgoing(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge)

        result = await handler.handle_webhook(
            {
                "event": "message_created",
                "message": {"message_type": "incoming", "content": "Hello"},
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_handle_webhook_ignores_private(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge)

        result = await handler.handle_webhook(
            {
                "event": "message_created",
                "message": {
                    "message_type": "outgoing",
                    "private": True,
                    "content": "Hello",
                },
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "ignored"

    def test_normalize_phone(self, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge)

        assert handler._normalize_phone("+1234567890") == "+1234567890"
        assert handler._normalize_phone("1234567890") == "+1234567890"
        assert handler._normalize_phone("+1 234 567 890") == "+1234567890"
