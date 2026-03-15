import pytest
from unittest.mock import Mock, AsyncMock, MagicMock


class TestStoreChatMessages:
    @pytest.mark.asyncio
    async def test_store_chat_messages_returns_stats(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=1)

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "test@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg1",
                            "from_me": False,
                            "from": "sender@s.whatsapp.net",
                            "text": "Hello",
                            "type": "text",
                            "timestamp": 1234567890,
                            "push_name": "Sender",
                        }
                    ],
                }
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 1
        assert stats["duplicates"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_store_chat_messages_counts_duplicates(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=None)

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "test@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg1",
                            "from_me": False,
                            "from": "sender@s.whatsapp.net",
                            "text": "Hello",
                            "type": "text",
                            "timestamp": 1234567890,
                        }
                    ],
                }
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 0
        assert stats["duplicates"] == 1
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_store_chat_messages_handles_errors(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock()
        tenant.message_store.add_with_persist = AsyncMock(
            side_effect=Exception("DB error")
        )

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "test@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg1",
                            "from_me": False,
                            "from": "sender@s.whatsapp.net",
                            "text": "Hello",
                            "type": "text",
                            "timestamp": 1234567890,
                        }
                    ],
                }
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 0
        assert stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_store_chat_messages_skips_messages_without_id(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=1)

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "test@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "from_me": False,
                            "from": "sender@s.whatsapp.net",
                            "text": "Hello",
                        },
                        {
                            "id": "msg2",
                            "from_me": False,
                            "from": "sender@s.whatsapp.net",
                            "text": "World",
                        },
                    ],
                }
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 1

    @pytest.mark.asyncio
    async def test_store_chat_messages_uses_add_when_no_add_with_persist(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock(spec=["add"])
        tenant.message_store.add = Mock()

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "test@s.whatsapp.net",
                    "is_group": False,
                    "messages": [
                        {
                            "id": "msg1",
                            "from_me": True,
                            "from": "me@s.whatsapp.net",
                            "text": "Outbound",
                            "type": "text",
                            "timestamp": 1234567890,
                        }
                    ],
                }
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 1
        tenant.message_store.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_chat_messages_handles_multiple_chats(self):
        from src.utils.history import store_chat_messages

        tenant = Mock()
        tenant.name = "test_tenant"
        tenant.message_store = Mock()
        tenant.message_store.add_with_persist = AsyncMock(return_value=1)

        db = Mock()

        chats_data = {
            "chats": [
                {
                    "jid": "chat1@s.whatsapp.net",
                    "is_group": False,
                    "messages": [{"id": "msg1", "from_me": False, "text": "Hello 1"}],
                },
                {
                    "jid": "chat2@s.whatsapp.net",
                    "is_group": True,
                    "messages": [{"id": "msg2", "from_me": True, "text": "Hello 2"}],
                },
            ]
        }

        stats = await store_chat_messages(tenant, chats_data, db)

        assert stats["stored"] == 2
