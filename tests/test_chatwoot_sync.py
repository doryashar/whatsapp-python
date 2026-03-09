import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.chatwoot import (
    ChatwootConfig,
    ChatwootContact,
    ChatwootConversation,
    ChatwootSyncService,
)


class TestChatwootSyncService:
    @pytest.fixture
    def mock_tenant(self):
        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.api_key_hash = "test_hash_123"
        return tenant

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=[])
        db.mark_message_chatwoot_synced = AsyncMock()
        return db

    @pytest.fixture
    def config(self):
        return ChatwootConfig(
            enabled=True,
            url="https://chatwoot.example.com",
            token="test_token",
            account_id="1",
            inbox_id=1,
            days_limit_import=3,
            import_messages=True,
        )

    @pytest.fixture
    def sync_service(self, config, mock_tenant, mock_db):
        return ChatwootSyncService(config, mock_tenant, mock_db)

    def test_extract_phone(self, config, mock_tenant, mock_db):
        service = ChatwootSyncService(config, mock_tenant, mock_db)

        phone = service._extract_phone("1234567890@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = service._extract_phone("1234567890:12@s.whatsapp.net")
        assert phone == "+1234567890"

        phone = service._extract_phone("invalid")
        assert phone is None

        phone = service._extract_phone("")
        assert phone is None

    @pytest.mark.asyncio
    async def test_sync_message_history_no_messages(self, sync_service, mock_db):
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=[])

        result = await sync_service.sync_message_history()

        assert result["synced"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == 0
        assert "No messages to sync" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_sync_message_history_basic(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Hello",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
            },
            {
                "id": 2,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Hi there",
                "msg_type": "text",
                "direction": "outbound",
                "push_name": "John Doe",
                "is_group": False,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(
            id=1, name="John Doe", phone_number="+1234567890"
        )
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ):
                with patch.object(sync_service._client, "create_message", AsyncMock()):
                    result = await sync_service.sync_message_history()

        assert result["synced"] == 2
        assert result["errors"] == 0
        assert mock_db.mark_message_chatwoot_synced.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_skip_duplicates(self, sync_service, mock_db):
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=[])

        result = await sync_service.sync_message_history()

        assert result["synced"] == 0
        assert "No messages to sync" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_sync_handles_errors(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Hello",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(
            id=1, name="John Doe", phone_number="+1234567890"
        )
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        from src.chatwoot.client import ChatwootAPIError

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ):
                with patch.object(
                    sync_service._client,
                    "create_message",
                    AsyncMock(side_effect=ChatwootAPIError("API error")),
                ):
                    result = await sync_service.sync_message_history()

        assert result["synced"] == 0
        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_sync_with_attachments(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "",
                "msg_type": "image",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
                "media_url": "https://example.com/image.jpg",
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(
            id=1, name="John Doe", phone_number="+1234567890"
        )
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ):
                with patch.object(
                    sync_service._client, "create_message", AsyncMock()
                ) as mock_create:
                    result = await sync_service.sync_message_history()

        assert result["synced"] == 1
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["attachments"] is not None
        assert len(call_kwargs["attachments"]) == 1

    @pytest.mark.asyncio
    async def test_sync_group_messages_skipped(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "group@g.us",
                "from_jid": "user@s.whatsapp.net",
                "text": "Group message",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "User",
                "is_group": True,
            },
        ]

        unsynced_messages = [
            {
                "id": 1,
                "chat_jid": "group@g.us",
                "from_jid": "user@s.whatsapp.net",
                "text": "Group message",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "User",
                "is_group": True,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=unsynced_messages
        )

        result = await sync_service.sync_message_history()

        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_sync_creates_contacts(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Hello",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(
            id=1, name="John Doe", phone_number="+1234567890"
        )
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ) as mock_find_contact:
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ):
                with patch.object(sync_service._client, "create_message", AsyncMock()):
                    await sync_service.sync_message_history()

        mock_find_contact.assert_called_once_with(
            phone_number="+1234567890", name="John Doe"
        )

    @pytest.mark.asyncio
    async def test_sync_reuses_conversations(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Message 1",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
            },
            {
                "id": 2,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Message 2",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John Doe",
                "is_group": False,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(
            id=1, name="John Doe", phone_number="+1234567890"
        )
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ) as mock_get_conv:
                with patch.object(sync_service._client, "create_message", AsyncMock()):
                    await sync_service.sync_message_history()

        mock_get_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_inbound_and_outbound(self, sync_service, mock_db):
        messages = [
            {
                "id": 1,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "1234567890@s.whatsapp.net",
                "text": "Incoming",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "John",
                "is_group": False,
            },
            {
                "id": 2,
                "chat_jid": "1234567890@s.whatsapp.net",
                "from_jid": "me",
                "text": "Outgoing",
                "msg_type": "text",
                "direction": "outbound",
                "push_name": "John",
                "is_group": False,
            },
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)

        mock_contact = ChatwootContact(id=1, name="John", phone_number="+1234567890")
        mock_conversation = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            sync_service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                sync_service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conversation),
            ):
                with patch.object(
                    sync_service._client, "create_message", AsyncMock()
                ) as mock_create:
                    await sync_service.sync_message_history()

        assert mock_create.call_count == 2
        calls = mock_create.call_args_list
        assert calls[0][1]["message_type"] == "incoming"
        assert calls[1][1]["message_type"] == "outgoing"

    @pytest.mark.asyncio
    async def test_close(self, sync_service):
        with patch.object(sync_service._client, "close", AsyncMock()) as mock_close:
            await sync_service.close()
            mock_close.assert_called_once()
