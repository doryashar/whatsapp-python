"""
Tests for chat history sync and tenant deletion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from src.store.messages import StoredMessage, MessageStore


class TestHistorySync:
    """Tests for chat history sync functionality."""

    @pytest.mark.asyncio
    async def test_handle_history_sync_stores_messages(self):
        """Test that handle_history_sync stores messages correctly."""
        from src.main import handle_history_sync

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.message_store = MagicMock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=1)

        chats_data = {
            "chats": [
                {
                    "jid": "1234567890@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg_1",
                            "from_me": False,
                            "from": "1234567890@s.whatsapp.net",
                            "text": "Hello",
                            "type": "text",
                            "timestamp": 1700000000000,
                            "push_name": "John",
                        },
                        {
                            "id": "msg_2",
                            "from_me": True,
                            "from": "0987654321@s.whatsapp.net",
                            "text": "Hi there",
                            "type": "text",
                            "timestamp": 1700000001000,
                        },
                    ],
                }
            ],
            "total_messages": 2,
        }

        with patch("src.main.tenant_manager") as mock_tm:
            mock_tm._db = MagicMock()
            await handle_history_sync(tenant, chats_data)

        assert tenant.message_store.add_with_persist.call_count == 2

        first_call = tenant.message_store.add_with_persist.call_args_list[0]
        first_msg = first_call[0][0]
        assert first_msg.id == "msg_1"
        assert first_msg.direction == "inbound"
        assert first_msg.text == "Hello"

        second_call = tenant.message_store.add_with_persist.call_args_list[1]
        second_msg = second_call[0][0]
        assert second_msg.id == "msg_2"
        assert second_msg.direction == "outbound"
        assert second_msg.text == "Hi there"

    @pytest.mark.asyncio
    async def test_handle_history_sync_handles_duplicates(self):
        """Test that handle_history_sync handles duplicate messages."""
        from src.main import handle_history_sync

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.message_store = MagicMock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=None)

        chats_data = {
            "chats": [
                {
                    "jid": "1234567890@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg_duplicate",
                            "from_me": False,
                            "from": "1234567890@s.whatsapp.net",
                            "text": "Duplicate",
                            "type": "text",
                            "timestamp": 1700000000000,
                        }
                    ],
                }
            ],
            "total_messages": 1,
        }

        with patch("src.main.tenant_manager") as mock_tm:
            mock_tm._db = MagicMock()
            await handle_history_sync(tenant, chats_data)

        tenant.message_store.add_with_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_history_sync_handles_missing_message_store(self):
        """Test that handle_history_sync handles missing message store."""
        from src.main import handle_history_sync

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.message_store = None

        chats_data = {
            "chats": [
                {
                    "jid": "1234567890@s.whatsapp.net",
                    "is_group": False,
                    "messages": [{"id": "msg_1"}],
                }
            ],
            "total_messages": 1,
        }

        with patch("src.main.tenant_manager") as mock_tm:
            mock_tm._db = MagicMock()
            await handle_history_sync(tenant, chats_data)


class TestTenantDeletion:
    """Tests for tenant deletion and cleanup."""

    @pytest.mark.asyncio
    async def test_delete_tenant_data_exists(self):
        """Test that delete_tenant_data method exists."""
        from src.store.database import Database

        assert hasattr(Database, "delete_tenant_data")

    def test_delete_tenant_data_signature(self):
        """Test delete_tenant_data has correct signature."""
        import inspect
        from src.store.database import Database

        sig = inspect.signature(Database.delete_tenant_data)
        params = list(sig.parameters)
        assert "self" in params
        assert "tenant_hash" in params


class TestMessageDeduplication:
    """Tests for message deduplication."""

    def test_stored_message_structure(self):
        """Test that StoredMessage has correct structure."""
        msg = StoredMessage(
            id="msg_123",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="John",
            text="Hello",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        assert msg.id == "msg_123"
        assert msg.direction == "inbound"
        assert msg.text == "Hello"

        msg_dict = msg.to_dict()
        assert msg_dict["id"] == "msg_123"
        assert msg_dict["direction"] == "inbound"


class TestSyncHistoryEndpoint:
    """Tests for the /api/sync-history endpoint."""

    def test_sync_history_endpoint_exists(self):
        """Test that the sync-history endpoint is registered."""
        from src.api.routes import router

        routes = [route.path for route in router.routes if hasattr(route, "path")]
        has_sync = any("/sync-history" in r for r in routes)
        assert has_sync, "Sync history endpoint should be registered"
