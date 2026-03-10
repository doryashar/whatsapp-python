import pytest
from unittest.mock import Mock, AsyncMock, patch
import json
import asyncio
import time

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
        assert config.bot_contact_enabled is True
        assert config.ignore_jids == []

    def test_config_custom_values(self):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=2,
            sign_messages=False,
            reopen_conversation=False,
            ignore_jids=["123456@s.whatsapp.net"],
        )
        assert config.enabled is True
        assert config.inbox_id == 2
        assert config.sign_messages is False
        assert config.reopen_conversation is False
        assert config.ignore_jids == ["123456@s.whatsapp.net"]


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
        assert msg.message_type == 0


class TestChatwootClient:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
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
            inbox_id=1,
            sign_messages=True,
        )

    def test_extract_phone(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        phone = integration._extract_phone("1234567890@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = integration._extract_phone("1234567890:12@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = integration._extract_phone("invalid")
        assert phone is None

    def test_is_ignored(self, mock_tenant):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            ignore_jids=["1234567890@s.whatsapp.net", "status@broadcast"],
        )
        integration = ChatwootIntegration(config, mock_tenant)

        assert integration._is_ignored("1234567890@s.whatsapp.net") is True
        assert integration._is_ignored("status@broadcast") is True
        assert integration._is_ignored("9876543210@s.whatsapp.net") is False
        assert integration._is_ignored(None) is False
        assert integration._is_ignored("") is False

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

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )

    def test_verify_signature_valid(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(
            mock_tenant, mock_bridge, config, hmac_token="secret"
        )

        payload = b'{"event": "test"}'
        signature = (
            "sha256="
            + __import__("hmac")
            .new(b"secret", payload, __import__("hashlib").sha256)
            .hexdigest()
        )

        assert handler.verify_signature(payload, signature) is True

    def test_verify_signature_invalid(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(
            mock_tenant, mock_bridge, config, hmac_token="secret"
        )

        payload = b'{"event": "test"}'
        signature = "sha256=invalid"

        assert handler.verify_signature(payload, signature) is False

    def test_verify_signature_no_token(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        assert handler.verify_signature(b"{}", "any") is True

    @pytest.mark.asyncio
    async def test_handle_webhook_ignores_non_outgoing(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler.handle_webhook(
            {
                "event": "message_created",
                "message": {"message_type": "incoming", "content": "Hello"},
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_handle_webhook_ignores_private(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

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

    def test_normalize_phone(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        assert handler._normalize_phone("+1234567890") == "+1234567890"
        assert handler._normalize_phone("1234567890") == "+1234567890"
        assert handler._normalize_phone("+1 234 567 890") == "+1234567890"

    def test_is_bot_contact(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        assert handler._is_bot_contact("123456") is True
        assert handler._is_bot_contact("+123456") is True
        assert handler._is_bot_contact("+123-456") is True
        assert handler._is_bot_contact("9876543210") is False

    def test_format_message_with_signature(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._format_message("Hello", "Agent Smith")
        assert "*Agent Smith:*" in result
        assert "Hello" in result

    def test_format_message_without_signature(self, mock_tenant, mock_bridge):
        config_no_sign = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            sign_messages=False,
        )
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config_no_sign)

        result = handler._format_message("Hello", "Agent Smith")
        assert result == "Hello"


class TestBotCommands:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            bot_contact_enabled=True,
            bot_name="Test Bot",
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        bridge.get_status = AsyncMock(
            return_value={
                "connection_state": "connected",
                "self": {"phone": "+1234567890"},
            }
        )
        bridge.logout = AsyncMock(return_value={"status": "logged_out"})
        bridge.login = AsyncMock(return_value={"status": "pending"})
        return bridge

    @pytest.mark.asyncio
    async def test_handle_status_command(self, config, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler._handle_status_command()
        assert "Connected" in result or "connected" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_disconnect_command(self, config, mock_tenant, mock_bridge):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler._handle_disconnect_command()
        assert "Disconnected" in result or "disconnected" in result.lower()


class TestChatwootConfigNewFields:
    def test_ignore_jids_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            ignore_jids=["1234567890@s.whatsapp.net"],
        )
        assert config.ignore_jids == ["1234567890@s.whatsapp.net"]

    def test_bot_contact_enabled_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            bot_contact_enabled=True,
            bot_name="Custom Bot",
        )
        assert config.bot_contact_enabled is True
        assert config.bot_name == "Custom Bot"

    def test_sign_delimiter_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            sign_delimiter="\n\n",
        )
        assert config.sign_delimiter == "\n\n"

    def test_empty_ignore_jids(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.ignore_jids == []


class TestMarkdownConversion:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            sign_messages=False,
        )

    def test_convert_bold(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._convert_markdown_formatting("**bold text**")
        assert result == "*bold text*"

    def test_convert_italic(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._convert_markdown_formatting("*italic text*")
        assert result == "_italic text_"

    def test_convert_strikethrough(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._convert_markdown_formatting("~~strikethrough~~")
        assert result == "~strikethrough~"

    def test_convert_code(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._convert_markdown_formatting("`code`")
        assert result == "```code```"

    def test_convert_mixed(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._convert_markdown_formatting("**bold** and *italic*")
        assert result == "*bold* and _italic_"

    def test_format_message_applies_conversion(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = handler._format_message("**Hello** world", None)
        assert result == "*Hello* world"


class TestMessageDeletion:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        bridge.delete_message = AsyncMock(return_value={"status": "deleted"})
        return bridge

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            message_delete_enabled=True,
        )

    @pytest.mark.asyncio
    async def test_handle_message_updated_deletes(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler._handle_message_updated(
            {
                "message": {
                    "content": "",
                    "source_id": "WAID:ABC123",
                },
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "deleted"
        mock_bridge.delete_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_updated_ignores_content(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler._handle_message_updated(
            {
                "message": {
                    "content": "updated content",
                    "source_id": "WAID:ABC123",
                },
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "acknowledged"
        mock_bridge.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_updated_disabled(self, mock_tenant, mock_bridge):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            message_delete_enabled=False,
        )
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        result = await handler._handle_message_updated(
            {
                "message": {
                    "content": "",
                    "source_id": "WAID:ABC123",
                },
                "sender": {"phone_number": "+1234567890"},
            }
        )

        assert result["status"] == "ignored"
        mock_bridge.delete_message.assert_not_called()


class TestReadStatusSync:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        bridge.send_message = AsyncMock(return_value={"status": "sent"})
        bridge.mark_read = AsyncMock(return_value={"status": "read"})
        return bridge

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            mark_read_on_reply=True,
        )

    @pytest.mark.asyncio
    async def test_mark_read_after_send(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        await handler.handle_webhook(
            {
                "event": "message_created",
                "message": {
                    "message_type": 1,  # Use integer,1
                    "content": "Hello",
                },
                "contact": {"phone_number": "+1234567890"},
            }
        )

        mock_bridge.mark_read.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_mark_read_when_disabled(self, mock_tenant, mock_bridge):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            mark_read_on_reply=False,
        )
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        await handler.handle_webhook(
            {
                "event": "message_created",
                "message": {
                    "message_type": 1,  # Use integer 1
                    "content": "Hello",
                },
                "contact": {"phone_number": "+1234567890"},
            }
        )

        mock_bridge.mark_read.assert_not_called()


class TestEvolutionApiConfigFields:
    def test_number_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            number="+1234567890",
        )
        assert config.number == "+1234567890"

    def test_auto_create_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            auto_create=False,
        )
        assert config.auto_create is False

    def test_organization_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            organization="My Company",
        )
        assert config.organization == "My Company"

    def test_logo_field(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            logo="https://example.com/logo.png",
        )
        assert config.logo == "https://example.com/logo.png"

    def test_defaults(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.number is None
        assert config.auto_create is True
        assert config.organization is None
        assert config.logo is None
        assert config.message_delete_enabled is True
        assert config.mark_read_on_reply is True
        assert config.group_messages_enabled is True


class TestGroupMessages:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            group_messages_enabled=True,
        )

    def test_extract_group_id(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        group_id = integration._extract_group_id("120363123456@g.us")
        assert group_id == "+120363123456"

        group_id = integration._extract_group_id("120363123456:12@g.us")
        assert group_id == "+120363123456"

        group_id = integration._extract_group_id("1234567890@s.whatsapp.net")
        assert group_id is None

        group_id = integration._extract_group_id(None)
        assert group_id is None

    @pytest.mark.asyncio
    async def test_group_message_disabled(self, mock_tenant, mock_bridge):
        config = ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            group_messages_enabled=False,
        )
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)

        result = await integration.handle_message(
            {
                "from": "1234567890@s.whatsapp.net",
                "chat_jid": "120363123456@g.us",
                "is_group": True,
                "text": "Hello group",
            }
        )
        assert result is False

    def test_format_group_contact_name(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        group_name = "Test Group"
        group_contact_name = f"{group_name} (GROUP)"
        assert group_contact_name == "Test Group (GROUP)"


class TestWAToCWMarkdownConversion:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )

    def test_convert_wa_bold_to_cw(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._convert_wa_to_cw_markdown("*bold text*")
        assert result == "**bold text**"

    def test_convert_wa_italic_to_cw(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._convert_wa_to_cw_markdown("_italic text_")
        assert result == "*italic text*"

    def test_convert_wa_strikethrough_to_cw(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._convert_wa_to_cw_markdown("~strikethrough~")
        assert result == "~~strikethrough~~"

    def test_convert_wa_code_to_cw(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._convert_wa_to_cw_markdown("```code```")
        assert result == "`code`"

    def test_convert_wa_mixed_to_cw(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._convert_wa_to_cw_markdown("*bold* and _italic_")
        assert result == "**bold** and *italic*"


class TestMessageTypes:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )

    def test_format_location_message(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._format_location_message(
            {
                "latitude": -23.5505,
                "longitude": -46.6333,
                "location_name": "São Paulo",
                "location_address": "Brazil",
            }
        )
        assert "-23.5505" in result
        assert "-46.6333" in result
        assert "São Paulo" in result
        assert "Brazil" in result

    def test_format_contact_message(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._format_contact_message(
            {"contacts": [{"name": "John Doe", "phones": ["+1234567890"]}]}
        )
        assert "John Doe" in result
        assert "+1234567890" in result

    def test_format_list_message_with_selection(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._format_list_message({"selected_text": "Option 1"})
        assert "Selected: Option 1" == result

    def test_format_list_message_without_selection(
        self, config, mock_tenant, mock_bridge
    ):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._format_list_message(
            {
                "list_title": "Menu",
                "list_description": "Choose an option",
                "button_text": "Click here",
            }
        )
        assert "Menu" in result
        assert "Choose an option" in result
        assert "Click here" in result

    def test_format_view_once_message(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._format_view_once_message({"media_type": "image"})
        assert "View Once Image" in result
        assert "cannot be displayed" in result


class TestMessageEditHandling:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )

    def test_prepare_message_content_edited(self, config, mock_tenant, mock_bridge):
        integration = ChatwootIntegration(config, mock_tenant, mock_bridge)
        result = integration._prepare_message_content(
            {
                "type": "text",
                "text": "Original message",
                "is_edited": True,
                "edited_text": "Edited message",
            },
            is_edited=True,
        )
        assert result == "\n\n*Edited:*\nEdited message"


class TestMessageDeletedHandler:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.api_key_hash = "test_hash"
        return tenant

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_handle_message_deleted_disabled(self, config, mock_tenant):
        config.enabled = False
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_message_deleted({"message_id": "123"})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_deleted_no_message_id(
        self, config, mock_tenant, mock_db
    ):
        integration = ChatwootIntegration(config, mock_tenant, db=mock_db)
        result = await integration.handle_message_deleted({})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_deleted_no_database(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_message_deleted({"message_id": "123"})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_deleted_message_not_found(
        self, config, mock_tenant, mock_db
    ):
        mock_db.get_message_by_id = AsyncMock(return_value=None)
        integration = ChatwootIntegration(config, mock_tenant, db=mock_db)
        result = await integration.handle_message_deleted({"message_id": "123"})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_deleted_no_chatwoot_ids(
        self, config, mock_tenant, mock_db
    ):
        mock_db.get_message_by_id = AsyncMock(
            return_value={
                "message_id": "123",
                "chatwoot_message_id": None,
                "chatwoot_conversation_id": None,
            }
        )
        integration = ChatwootIntegration(config, mock_tenant, db=mock_db)
        result = await integration.handle_message_deleted({"message_id": "123"})
        assert result is False


class TestMessageReadHandler:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.mark.asyncio
    async def test_handle_message_read_disabled(self, config, mock_tenant):
        config.enabled = False
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_message_read(
            {"chat_jid": "1234567890@s.whatsapp.net"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_read_no_chat_jid(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_message_read({})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_read_invalid_jid(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_message_read({"chat_jid": "invalid"})
        assert result is False


class TestConversationCacheTTL:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
        )

    def test_cache_initially_empty(self, config):
        from src.chatwoot.client import ChatwootClient

        client = ChatwootClient(config)
        assert client._conversation_cache == {}

    def test_cache_conversation(self, config):
        import time
        from src.chatwoot.client import ChatwootClient
        from src.chatwoot.models import ChatwootConversation

        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        client._cache_conversation(1, conv)

        assert 1 in client._conversation_cache
        cached_conv, timestamp = client._conversation_cache[1]
        assert cached_conv == conv
        assert time.time() - timestamp < 1

    def test_get_cached_conversation_within_ttl(self, config):
        import time
        from src.chatwoot.client import ChatwootClient
        from src.chatwoot.models import ChatwootConversation

        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        client._cache_conversation(1, conv)

        cached = client._get_cached_conversation(1)
        assert cached == conv

    def test_get_cached_conversation_expired_ttl(self, config):
        import time
        from src.chatwoot.client import ChatwootClient
        from src.chatwoot.models import ChatwootConversation

        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        client._conversation_cache[1] = (conv, time.time() - 2000)

        cached = client._get_cached_conversation(1)
        assert cached is None
        assert 1 not in client._conversation_cache

    def test_clear_cache(self, config):
        from src.chatwoot.client import ChatwootClient
        from src.chatwoot.models import ChatwootConversation

        client = ChatwootClient(config)
        conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        client._cache_conversation(1, conv)
        client.clear_cache()
        assert client._conversation_cache == {}


class TestErrorPrivateNotes:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        return tenant

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        bridge.send_message = AsyncMock(side_effect=Exception("Send failed"))
        return bridge

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )

    @pytest.mark.asyncio
    async def test_error_creates_private_note(self, mock_tenant, mock_bridge, config):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        with patch.object(
            handler, "_create_error_private_note", new_callable=AsyncMock
        ) as mock_note:
            result = await handler.handle_webhook(
                {
                    "event": "message_created",
                    "message": {
                        "message_type": 1,
                        "content": "Hello",
                    },
                    "contact": {"phone_number": "+1234567890"},
                }
            )

            assert result["status"] == "error"
            mock_note.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_error_private_note_with_conversation(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        mock_client = AsyncMock()
        mock_client.create_message = AsyncMock()
        handler._chatwoot_client = mock_client

        await handler._create_error_private_note({"id": 123}, "Test error")

        mock_client.create_message.assert_called_once_with(
            conversation_id=123,
            content="Failed to send to WhatsApp: Test error",
            private=True,
        )

    @pytest.mark.asyncio
    async def test_create_error_private_note_without_conversation(
        self, mock_tenant, mock_bridge, config
    ):
        handler = ChatwootWebhookHandler(mock_tenant, mock_bridge, config)

        await handler._create_error_private_note({}, "Test error")
        await handler._create_error_private_note(None, "Test error")


class TestGroupMessagesEnabledField:
    def test_group_messages_enabled_default(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.group_messages_enabled is True

    def test_group_messages_enabled_false(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            group_messages_enabled=False,
        )
        assert config.group_messages_enabled is False


class TestConversationLock:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            conversation_lock_enabled=True,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.api_key_hash = "test_hash"
        return tenant

    def test_conversation_lock_default(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.conversation_lock_enabled is True

    def test_conversation_lock_disabled(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            conversation_lock_enabled=False,
        )
        assert config.conversation_lock_enabled is False

    @pytest.mark.asyncio
    async def test_get_conversation_lock(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        lock1 = integration._get_conversation_lock("test_jid_1")
        lock2 = integration._get_conversation_lock("test_jid_2")
        lock1_again = integration._get_conversation_lock("test_jid_1")

        assert lock1 is lock1_again
        assert lock1 is not lock2
        assert isinstance(lock1, asyncio.Lock)


class TestLidContactHandling:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            lid_contact_handling_enabled=True,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.api_key_hash = "test_hash"
        return tenant

    def test_lid_handling_default(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.lid_contact_handling_enabled is True

    def test_lid_handling_disabled(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            lid_contact_handling_enabled=False,
        )
        assert config.lid_contact_handling_enabled is False

    @pytest.mark.asyncio
    async def test_handle_lid_contact_update_with_lid(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        with patch.object(
            integration._client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
        ) as mock_find:
            with patch.object(
                integration._client,
                "update_contact",
                new_callable=AsyncMock,
            ) as mock_update:
                mock_find.return_value = ChatwootContact(
                    id=123,
                    phone_number="+1234567890",
                    name="Test",
                    identifier="old@s.whatsapp.net",
                )

                await integration._handle_lid_contact_update("+1234567890", "test@lid")

                mock_update.assert_called_once_with(
                    contact_id=123,
                    identifier="test@lid",
                )

    @pytest.mark.asyncio
    async def test_handle_lid_contact_update_without_lid(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        with patch.object(
            integration._client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
        ) as mock_find:
            await integration._handle_lid_contact_update(
                "+1234567890", "test@s.whatsapp.net"
            )

            mock_find.assert_not_called()


class TestStatusInstance:
    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            status_instance_enabled=True,
            bot_contact_enabled=True,
        )

    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.api_key_hash = "test_hash"
        return tenant

    @pytest.mark.asyncio
    async def test_status_instance_disabled(self, config, mock_tenant):
        config.enabled = False
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_status_instance({"status": "connected"})
        assert result is False

    @pytest.mark.asyncio
    async def test_status_instance_feature_disabled(self, config, mock_tenant):
        config.status_instance_enabled = False
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_status_instance({"status": "connected"})
        assert result is False

    @pytest.mark.asyncio
    async def test_status_instance_bot_contact_disabled(self, config, mock_tenant):
        config.bot_contact_enabled = False
        integration = ChatwootIntegration(config, mock_tenant)
        result = await integration.handle_status_instance({"status": "connected"})
        assert result is False

    @pytest.mark.asyncio
    async def test_status_instance_cooldown(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)
        integration._last_connection_notification = time.time()

        result = await integration.handle_status_instance({"status": "connected"})
        assert result is False

    @pytest.mark.asyncio
    async def test_status_instance_success(self, config, mock_tenant):
        integration = ChatwootIntegration(config, mock_tenant)

        with patch.object(
            integration._client,
            "find_or_create_bot_contact",
            new_callable=AsyncMock,
        ) as mock_bot:
            with patch.object(
                integration._client,
                "get_or_create_bot_conversation",
                new_callable=AsyncMock,
            ) as mock_conv:
                with patch.object(
                    integration._client,
                    "create_message",
                    new_callable=AsyncMock,
                ) as mock_msg:
                    mock_bot.return_value = ChatwootContact(
                        id=999,
                        phone_number="+123456",
                        name="Bot",
                    )
                    mock_conv.return_value = ChatwootConversation(
                        id=888,
                        account_id=1,
                        inbox_id=1,
                        contact_id=999,
                    )

                    result = await integration.handle_status_instance(
                        {"status": "connected"}
                    )

                    assert result is True
                    mock_msg.assert_called_once()
                    call_args = mock_msg.call_args
                    assert call_args[1]["content"] == "WhatsApp status: connected"
                    assert call_args[1]["message_type"] == "incoming"

    def test_status_instance_enabled_default(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
        )
        assert config.status_instance_enabled is True

    def test_status_instance_enabled_false(self):
        config = ChatwootConfig(
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            status_instance_enabled=False,
        )
        assert config.status_instance_enabled is False
