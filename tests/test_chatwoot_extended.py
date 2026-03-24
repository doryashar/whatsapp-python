import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
import json
import asyncio
import time

from src.chatwoot import (
    ChatwootConfig,
    ChatwootContact,
    ChatwootConversation,
    ChatwootMessage,
    ChatwootClient,
    ChatwootAPIError,
    ChatwootIntegration,
    ChatwootSyncService,
)


def _make_config(**overrides):
    defaults = {
        "enabled": True,
        "url": "https://chatwoot.example.com",
        "token": "test_token",
        "account_id": "1",
        "inbox_id": 1,
    }
    defaults.update(overrides)
    return ChatwootConfig(**defaults)


def _make_tenant(**overrides):
    tenant = Mock()
    tenant.name = overrides.pop("name", "test_tenant")
    tenant.api_key_hash = overrides.pop("api_key_hash", "test_hash")
    for k, v in overrides.items():
        setattr(tenant, k, v)
    return tenant


class TestChatwootClientHTTPErrorHandling:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.mark.asyncio
    async def test_request_400_raises_api_error(self, config):
        client = ChatwootClient(config)

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}
        mock_response.text = '{"error": "Bad request"}'

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        with pytest.raises(ChatwootAPIError, match="Bad request") as exc_info:
            await client._request("POST", "/api/v1/test")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_500_raises_api_error(self, config):
        client = ChatwootClient(config)

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal server error"}
        mock_response.text = '{"message": "Internal server error"}'

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        with pytest.raises(ChatwootAPIError, match="Internal server error"):
            await client._request("POST", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_timeout_raises_api_error(self, config):
        client = ChatwootClient(config)

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        client._client = mock_http_client

        with pytest.raises(ChatwootAPIError, match="Timeout"):
            await client._request("GET", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_connection_error_raises_api_error(self, config):
        client = ChatwootClient(config)

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(
            side_effect=httpx.ConnectError("connection failed")
        )
        client._client = mock_http_client

        with pytest.raises(ChatwootAPIError, match="Connection error"):
            await client._request("GET", "/api/v1/test")

    @pytest.mark.asyncio
    async def test_request_non_json_error_response(self, config):
        client = ChatwootClient(config)

        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.json.side_effect = Exception("not json")
        mock_response.text = "Bad Gateway"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        with pytest.raises(ChatwootAPIError) as exc_info:
            await client._request("GET", "/api/v1/test")

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_successful_request_returns_json(self, config):
        client = ChatwootClient(config)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "Test"}

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        result = await client._request("GET", "/api/v1/test")
        assert result == {"id": 1, "name": "Test"}


class TestChatwootClientContactMethods:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.mark.asyncio
    async def test_find_contact_by_phone_empty_response(self, config):
        client = ChatwootClient(config)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"payload": {"contacts": []}}
            result = await client.find_contact_by_phone("+1234567890")
            assert result is None

    @pytest.mark.asyncio
    async def test_find_contact_by_phone_match(self, config):
        client = ChatwootClient(config)
        contact_data = {
            "id": 1,
            "name": "John",
            "phone_number": "+1234567890",
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"payload": {"contacts": [contact_data]}}
            result = await client.find_contact_by_phone("+1234567890")
            assert result is not None
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_find_contact_by_identifier(self, config):
        client = ChatwootClient(config)
        contact_data = {
            "id": 5,
            "name": "Jane",
            "identifier": "test@s.whatsapp.net",
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"payload": {"contacts": [contact_data]}}
            result = await client.find_contact_by_identifier("test@s.whatsapp.net")
            assert result is not None
            assert result.identifier == "test@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_create_contact_requires_inbox_id(self, config):
        config_no_inbox = _make_config(inbox_id=None)
        client = ChatwootClient(config_no_inbox)

        with pytest.raises(ChatwootAPIError, match="inbox_id not configured"):
            await client.create_contact("+1234567890", "John")

    @pytest.mark.asyncio
    async def test_update_contact_with_avatar_url(self, config):
        client = ChatwootClient(config)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "id": 1,
                "name": "John",
                "phone_number": "+1234567890",
                "thumbnail": "https://example.com/avatar.jpg",
            }
            result = await client.update_contact(
                contact_id=1, avatar_url="https://example.com/avatar.jpg"
            )
            assert result.thumbnail == "https://example.com/avatar.jpg"

    @pytest.mark.asyncio
    async def test_find_or_create_contact_updates_name(self, config):
        client = ChatwootClient(config)
        existing = ChatwootContact(id=1, name="Old Name", phone_number="+1234567890")

        with patch.object(
            client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch.object(
                client, "update_contact", new_callable=AsyncMock
            ) as mock_update:
                mock_update.return_value = ChatwootContact(
                    id=1, name="New Name", phone_number="+1234567890"
                )
                result = await client.find_or_create_contact("+1234567890", "New Name")
                mock_update.assert_called_once()
                assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_find_or_create_contact_does_not_update_same_name(self, config):
        client = ChatwootClient(config)
        existing = ChatwootContact(id=1, name="John", phone_number="+1234567890")

        with patch.object(
            client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch.object(
                client, "update_contact", new_callable=AsyncMock
            ) as mock_update:
                result = await client.find_or_create_contact("+1234567890", "John")
                mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_find_or_create_contact_no_match_creates(self, config):
        client = ChatwootClient(config)

        with patch.object(
            client, "find_contact_by_phone", new_callable=AsyncMock, return_value=None
        ):
            with patch.object(
                client, "create_contact", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = ChatwootContact(
                    id=2, name="New", phone_number="+1234567890"
                )
                result = await client.find_or_create_contact("+1234567890", "New")
                mock_create.assert_called_once()


class TestChatwootClientConversationMethods:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.mark.asyncio
    async def test_create_conversation_requires_inbox_id(self, config):
        config_no_inbox = _make_config(inbox_id=None)
        client = ChatwootClient(config_no_inbox)

        with pytest.raises(ChatwootAPIError, match="inbox_id not configured"):
            await client.create_conversation(contact_id=1)

    @pytest.mark.asyncio
    async def test_find_conversation_empty_result(self, config):
        client = ChatwootClient(config)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": {"payload": {"conversations": []}}}
            result = await client.find_conversation_by_contact(1)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_reuses_cached(self, config):
        client = ChatwootClient(config)
        contact = ChatwootContact(id=1, name="Test", phone_number="+1234567890")
        conv = ChatwootConversation(
            id=10, account_id=1, inbox_id=1, contact_id=1, status="open"
        )
        client._conversation_cache[1] = (conv, time.time())

        result = await client.get_or_create_conversation(contact)
        assert result.id == 10

    @pytest.mark.asyncio
    async def test_get_or_create_reopens_resolved(self, config):
        config.reopen_conversation = True
        client = ChatwootClient(config)
        contact = ChatwootContact(id=1, name="Test", phone_number="+1234567890")
        resolved_conv = ChatwootConversation(
            id=10, account_id=1, inbox_id=1, contact_id=1, status="resolved"
        )

        with patch.object(
            client,
            "find_conversation_by_contact",
            new_callable=AsyncMock,
            return_value=resolved_conv,
        ):
            with patch.object(
                client, "toggle_conversation_status", new_callable=AsyncMock
            ) as mock_toggle:
                result = await client.get_or_create_conversation(contact)
                mock_toggle.assert_called_once_with(10, "open")

    @pytest.mark.asyncio
    async def test_delete_message_404_returns_false(self, config):
        client = ChatwootClient(config)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = ChatwootAPIError("not found", status_code=404)
            result = await client.delete_message(conversation_id=1, message_id=99)
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_message_non_404_raises(self, config):
        client = ChatwootClient(config)

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = ChatwootAPIError("server error", status_code=500)
            with pytest.raises(ChatwootAPIError, match="server error"):
                await client.delete_message(conversation_id=1, message_id=99)


class TestChatwootIntegrationContentFormatting:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    def test_prepare_content_text(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "text", "text": "Hello"})
        assert result == "Hello"

    def test_prepare_content_text_empty(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "text", "text": ""})
        assert result is None

    def test_prepare_content_location_no_coords(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "location"})
        assert result == "[Location]"

    def test_prepare_content_location_with_coords(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "location",
                "latitude": 40.0,
                "longitude": -74.0,
            }
        )
        assert "40.0" in result
        assert "-74.0" in result
        assert "Location:" in result

    def test_prepare_content_location_with_name_and_address(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "location",
                "latitude": 40.0,
                "longitude": -74.0,
                "location_name": "NYC",
                "location_address": "New York, NY",
            }
        )
        assert "NYC" in result
        assert "New York, NY" in result

    def test_prepare_content_contact_empty(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "contact"})
        assert result == "[Contact]"

    def test_prepare_content_contact_with_data(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "contact",
                "contact_name": "John",
                "contact_phone": "+1234567890",
            }
        )
        assert "John" in result
        assert "+1234567890" in result

    def test_prepare_content_contact_with_list(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "contact",
                "contacts": [
                    {"name": "John", "phones": ["+111", "+222"]},
                    {"name": "Jane", "phones": []},
                ],
            }
        )
        assert "John" in result
        assert "+111" in result
        assert "+222" in result
        assert "Jane" in result

    def test_prepare_content_list_no_data(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "list"})
        assert result == "[List Message]"

    def test_prepare_content_list_with_all_fields(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "list",
                "list_title": "Menu",
                "list_description": "Pick one",
                "button_text": "Select",
            }
        )
        assert "Menu" in result
        assert "Pick one" in result
        assert "Select" in result

    def test_prepare_content_view_once(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {"type": "viewOnce", "media_type": "video"}
        )
        assert "View Once Video" in result
        assert "cannot be displayed" in result

    def test_prepare_content_fallback_for_media(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {
                "type": "image",
                "text": "caption text",
            }
        )
        assert result == "caption text"

    def test_prepare_content_empty_media(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content({"type": "image"})
        assert result is None

    def test_prepare_content_edited_appends(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = integration._prepare_message_content(
            {"type": "text", "text": "Original", "edited_text": "New"},
            is_edited=True,
        )
        assert "Original" in result
        assert "New" in result
        assert "Edited to" in result


class TestChatwootIntegrationAttachments:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    @pytest.mark.asyncio
    async def test_prepare_attachments_image(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration._prepare_attachments(
            {
                "media_url": "https://example.com/img.jpg",
                "type": "image",
                "mimetype": "image/jpeg",
                "filename": "photo.jpg",
            }
        )
        assert len(result) == 1
        assert result[0]["file_type"] == "image/jpeg"
        assert result[0]["file_url"] == "https://example.com/img.jpg"

    @pytest.mark.asyncio
    async def test_prepare_attachments_video(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration._prepare_attachments(
            {
                "media_url": "https://example.com/vid.mp4",
                "type": "video",
                "mimetype": "video/mp4",
            }
        )
        assert result[0]["file_type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_prepare_attachments_no_url(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration._prepare_attachments({"type": "image"})
        assert result == []


class TestChatwootIntegrationConversationLock:
    @pytest.fixture
    def config(self):
        return _make_config(conversation_lock_enabled=True)

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    @pytest.mark.asyncio
    async def test_conversation_lock_timeout(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        integration.LOCK_TIMEOUT = 0.001

        contact = ChatwootContact(id=1, name="Test", phone_number="+123")

        async def slow_get_or_create(**kwargs):
            await asyncio.sleep(1)
            return ChatwootConversation(
                id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
            )

        first_lock = await integration._get_conversation_lock("jid1")
        await first_lock.acquire()

        with patch.object(
            integration._client,
            "get_or_create_conversation",
            new_callable=AsyncMock,
            side_effect=slow_get_or_create,
        ):
            result = await integration._get_or_create_conversation_with_lock(
                contact, "jid1"
            )
            assert result is not None

        first_lock.release()

    @pytest.mark.asyncio
    async def test_lock_caches_conversation(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        contact = ChatwootContact(id=1, name="Test", phone_number="+123")
        conv = ChatwootConversation(
            id=10, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            integration._client,
            "get_or_create_conversation",
            new_callable=AsyncMock,
            return_value=conv,
        ):
            result = await integration._get_or_create_conversation_with_lock(
                contact, "jid1"
            )
            assert result.id == 10

        cached = integration._conversation_cache.get(contact.id)
        assert cached is not None
        assert cached.id == 10


class TestChatwootSyncEdgeCases:
    @pytest.fixture
    def config(self):
        return _make_config(days_limit_import=3)

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=[])
        db.mark_message_chatwoot_synced = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_sync_custom_days_limit(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=[])

        result = await service.sync_message_history(days_limit=7)
        assert result["synced"] == 0
        mock_db.get_unsynced_messages_for_chatwoot.assert_called_once_with(
            tenant_hash="test_hash",
            days_limit=7,
            limit=1000,
        )

    @pytest.mark.asyncio
    async def test_sync_single_message_skipped_on_empty_text(
        self, config, tenant, mock_db
    ):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "123@s.whatsapp.net",
                    "from_jid": "123@s.whatsapp.net",
                    "text": "",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )
        mock_contact = ChatwootContact(id=1, name="Test", phone_number="+123")
        mock_conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conv),
            ):
                result = await service.sync_message_history()

        assert result["synced"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_sync_contact_phone_extraction_failure(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "invalid_jid",
                    "text": "Hello",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )
        result = await service.sync_message_history()
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_sync_contact_creation_failure(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "123@s.whatsapp.net",
                    "text": "Hello",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(side_effect=ChatwootAPIError("API error")),
        ):
            result = await service.sync_message_history()

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_sync_conversation_creation_failure(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "123@s.whatsapp.net",
                    "text": "Hello",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )
        mock_contact = ChatwootContact(id=1, name="Test", phone_number="+123")

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                service._client,
                "get_or_create_conversation",
                AsyncMock(side_effect=Exception("DB error")),
            ):
                result = await service.sync_message_history()

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_sync_contact_creation_failure(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "1234567890@s.whatsapp.net",
                    "text": "Hello",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(side_effect=ChatwootAPIError("API error")),
        ):
            result = await service.sync_message_history()

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_sync_conversation_creation_failure(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "chat_jid": "1234567890@s.whatsapp.net",
                    "text": "Hello",
                    "msg_type": "text",
                    "direction": "inbound",
                    "push_name": "Test",
                    "is_group": False,
                },
            ]
        )
        mock_contact = ChatwootContact(id=1, name="Test", phone_number="+1234567890")

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ):
            with patch.object(
                service._client,
                "get_or_create_conversation",
                AsyncMock(side_effect=Exception("DB error")),
            ):
                result = await service.sync_message_history()

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_sync_deduplication_uses_cache(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)
        messages = [
            {
                "id": i,
                "chat_jid": "1234567890@s.whatsapp.net",
                "text": f"msg{i}",
                "msg_type": "text",
                "direction": "inbound",
                "push_name": "Test",
                "is_group": False,
            }
            for i in range(3)
        ]
        mock_db.get_unsynced_messages_for_chatwoot = AsyncMock(return_value=messages)
        mock_contact = ChatwootContact(id=1, name="Test", phone_number="+1234567890")
        mock_conv = ChatwootConversation(
            id=1, account_id=1, inbox_id=1, contact_id=1, status="open"
        )

        with patch.object(
            service._client,
            "find_or_create_contact",
            AsyncMock(return_value=mock_contact),
        ) as mock_foc:
            with patch.object(
                service._client,
                "get_or_create_conversation",
                AsyncMock(return_value=mock_conv),
            ) as mock_goc:
                with patch.object(service._client, "create_message", AsyncMock()):
                    await service.sync_message_history()

        mock_foc.assert_called_once()
        mock_goc.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_media_types(self, config, tenant, mock_db):
        service = ChatwootSyncService(config, tenant, mock_db)

        for msg_type, expected_mime in [
            ("image", "image/jpeg"),
            ("video", "video/mp4"),
            ("audio", "audio/ogg"),
            ("document", "application/pdf"),
            ("sticker", "image/webp"),
            ("unknown", "application/octet-stream"),
        ]:
            result = await service._prepare_attachment(
                "https://url.com/file", msg_type, {}
            )
            assert result is not None
            assert result[0]["file_type"] == expected_mime
            assert result[0]["file_url"] == "https://url.com/file"


class TestChatwootIntegrationLidHandling:
    @pytest.fixture
    def config(self):
        return _make_config(lid_contact_handling_enabled=True)

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    @pytest.mark.asyncio
    async def test_lid_contact_update_identifier_same(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)

        with patch.object(
            integration._client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
            return_value=ChatwootContact(
                id=1, phone_number="+123", identifier="test@lid"
            ),
        ) as mock_find:
            with patch.object(
                integration._client, "update_contact", new_callable=AsyncMock
            ) as mock_update:
                await integration._handle_lid_contact_update("+123", "test@lid")
                mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_lid_contact_update_contact_not_found(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)

        with patch.object(
            integration._client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch.object(
                integration._client, "update_contact", new_callable=AsyncMock
            ) as mock_update:
                await integration._handle_lid_contact_update("+123", "test@lid")
                mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_lid_contact_update_exception_handled(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)

        with patch.object(
            integration._client,
            "find_contact_by_phone",
            new_callable=AsyncMock,
            side_effect=Exception("network error"),
        ):
            await integration._handle_lid_contact_update("+123", "test@lid")


class TestChatwootIntegrationEdgeCases:
    @pytest.fixture
    def config(self):
        return _make_config()

    @pytest.fixture
    def tenant(self):
        return _make_tenant()

    @pytest.mark.asyncio
    async def test_handle_message_empty_type(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_message({"type": "empty"})
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_empty_text(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_message(
            {
                "type": "text",
                "text": "   ",
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_message_ignored_jid(self, config, tenant):
        config.ignore_jids = ["1234567890@s.whatsapp.net"]
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_message(
            {
                "from": "1234567890@s.whatsapp.net",
                "chat_jid": "1234567890@s.whatsapp.net",
                "text": "Hello",
                "type": "text",
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_direct_message_invalid_phone(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_message(
            {
                "from": "invalid",
                "chat_jid": "invalid",
                "text": "Hello",
                "type": "text",
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_group_message_invalid_group_id(self, config, tenant):
        config.group_messages_enabled = True
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_message(
            {
                "from": "user@s.whatsapp.net",
                "chat_jid": "invalid",
                "is_group": True,
                "text": "Hello",
                "type": "text",
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_extract_group_id_already_has_plus(self):
        config = _make_config()
        tenant = _make_tenant()
        integration = ChatwootIntegration(config, tenant)
        result = integration._extract_group_id("+120363123456@g.us")
        assert result == "+120363123456"

    @pytest.mark.asyncio
    async def test_connected_event(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_connected({"phone": "+1234567890"})
        assert result is True

    @pytest.mark.asyncio
    async def test_disconnected_event(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_disconnected({})
        assert result is True

    @pytest.mark.asyncio
    async def test_qr_event_no_qr_data(self, config, tenant):
        config.bot_contact_enabled = True
        integration = ChatwootIntegration(config, tenant)
        result = await integration.handle_qr({})
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_cache(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        integration._contact_cache.set("key1", "val1")
        integration._conversation_cache.set("key2", "val2")
        await integration.clear_cache()
        assert integration._contact_cache.get("key1") is None
        assert integration._conversation_cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_close(self, config, tenant):
        integration = ChatwootIntegration(config, tenant)
        integration._conversation_locks["jid1"] = asyncio.Lock()
        with patch.object(integration._client, "close", new_callable=AsyncMock):
            await integration.close()
        assert len(integration._conversation_locks) == 0
