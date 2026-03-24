import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, UTC
from pathlib import Path

from src.store.database import Database, is_transient_error, DATABASE_RETRY_ATTEMPTS


class TestIsTransientError:
    def test_connection_error_is_transient(self):
        error = Exception("could not connect to server: Connection refused")
        assert is_transient_error(error) is True

    def test_timeout_is_transient(self):
        error = Exception("connection timeout expired")
        assert is_transient_error(error) is True

    def test_deadlock_is_transient(self):
        error = Exception("deadlock detected")
        assert is_transient_error(error) is True

    def test_locked_is_transient(self):
        error = Exception("database is locked")
        assert is_transient_error(error) is True

    def test_busy_is_transient(self):
        error = Exception("database is busy")
        assert is_transient_error(error) is True

    def test_too_many_connections_is_transient(self):
        error = Exception("too many connections")
        assert is_transient_error(error) is True

    def test_connection_pool_is_transient(self):
        error = Exception("connection pool exhausted")
        assert is_transient_error(error) is True

    def test_unique_constraint_not_transient(self):
        error = Exception("UNIQUE constraint failed: tenants.api_key_hash")
        assert is_transient_error(error) is False

    def test_foreign_key_not_transient(self):
        error = Exception("FOREIGN KEY constraint failed")
        assert is_transient_error(error) is False

    def test_generic_error_not_transient(self):
        error = Exception("some random error")
        assert is_transient_error(error) is False

    def test_connection_pool_is_transient(self):
        error = Exception("connection pool exhausted")
        assert is_transient_error(error) is True

    def test_case_insensitive(self):
        error = Exception("Connection TIMEOUT while talking to Database")
        assert is_transient_error(error) is True

    def test_empty_error_message(self):
        error = Exception("")
        assert is_transient_error(error) is False


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        db = Database("", Path("/tmp"))
        operation = AsyncMock(return_value="success")
        result = await db._with_retry(operation)
        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        db = Database("", Path("/tmp"))
        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("connection timeout")
            return "recovered"

        with patch("src.store.database.asyncio.sleep", new_callable=AsyncMock):
            result = await db._with_retry(flaky_operation)
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self):
        db = Database("", Path("/tmp"))
        operation = AsyncMock(side_effect=Exception("database is locked"))

        with patch("src.store.database.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="database is locked"):
                await db._with_retry(operation)

        assert operation.call_count == DATABASE_RETRY_ATTEMPTS

    @pytest.mark.asyncio
    async def test_raises_non_transient_immediately(self):
        db = Database("", Path("/tmp"))
        operation = AsyncMock(side_effect=Exception("UNIQUE constraint failed"))

        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            await db._with_retry(operation)

        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        db = Database("", Path("/tmp"))
        operation = AsyncMock(side_effect=Exception("connection refused"))

        with patch(
            "src.store.database.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(Exception):
                await db._with_retry(operation)

        assert mock_sleep.call_count == DATABASE_RETRY_ATTEMPTS - 1
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]


class TestPostgresConnectionDetection:
    def test_postgresql_url_detected(self):
        db = Database("postgresql://user:pass@localhost/db", Path("/tmp"))
        assert db._is_postgres is True

    def test_postgres_url_detected(self):
        db = Database("postgres://user:pass@localhost/db", Path("/tmp"))
        assert db._is_postgres is True

    def test_sqlite_url_detected(self):
        db = Database("", Path("/tmp"))
        assert db._is_postgres is False

    def test_file_url_detected(self):
        db = Database("file:///tmp/db.sqlite", Path("/tmp"))
        assert db._is_postgres is False

    @pytest.mark.asyncio
    async def test_connect_uses_asyncpg_for_postgres(self):
        db = Database("postgresql://user:pass@host/db", Path("/tmp"))
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.close = AsyncMock()

        with patch(
            "asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool
        ) as mock_create:
            await db.connect()

        mock_create.assert_called_once_with("postgresql://user:pass@host/db")
        assert db._pool == mock_pool

    @pytest.mark.asyncio
    async def test_connect_creates_postgres_tables(self):
        db = Database("postgresql://user:pass@host/db", Path("/tmp"))
        mock_conn = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )
        mock_pool.close = AsyncMock()

        with patch(
            "asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool
        ) as mock_create:
            await db.connect()

        mock_create.assert_called_once()
        assert db._pool is mock_pool

    @pytest.mark.asyncio
    async def test_connect_uses_aiosqlite_for_sqlite(self):
        db = Database("", Path("/tmp"))
        mock_conn = AsyncMock()

        with patch(
            "aiosqlite.connect", new_callable=AsyncMock, return_value=mock_conn
        ) as mock_connect:
            await db.connect()

        mock_connect.assert_called_once()
        mock_conn.execute.assert_any_call("PRAGMA journal_mode=WAL")


class TestUpdateTenantEnabled:
    @pytest.mark.asyncio
    async def test_enable_tenant_sqlite(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.update_tenant_enabled("hash1", False)
        tenants = await db.load_tenants()
        assert tenants[0]["enabled"] is False

    @pytest.mark.asyncio
    async def test_disable_tenant_sqlite(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.update_tenant_enabled("hash1", True)
        tenants = await db.load_tenants()
        assert tenants[0]["enabled"] is True


class TestPopulateContactsFromMessages:
    @pytest.mark.asyncio
    async def test_populate_from_empty_db(self, db):
        count = await db.populate_contacts_from_messages("nonexistent")
        assert count == 0

    @pytest.mark.asyncio
    async def test_populate_contacts_from_messages_sqlite(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            push_name="John Doe",
            text="Hello",
            timestamp=1000,
        )
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg2",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            push_name="John Doe",
            text="World",
            timestamp=2000,
        )
        count = await db.populate_contacts_from_messages("hash1")
        assert count >= 1


class TestCleanupOldData:
    @pytest.mark.asyncio
    async def test_cleanup_empty_db(self, db):
        result = await db.cleanup_old_data(days=7)
        assert result["webhook_attempts"] == 0
        assert result["messages"] == 0
        assert result["admin_sessions"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_does_not_remove_recent_data(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            text="Hello",
            timestamp=1000,
        )
        result = await db.cleanup_old_data(days=7)
        assert result["messages"] == 0


class TestGetContactNamesForChats:
    @pytest.mark.asyncio
    async def test_empty_result(self, db):
        names = await db.get_contact_names_for_chats(["hash1"], ["123@s.whatsapp.net"])
        assert names == {}

    @pytest.mark.asyncio
    async def test_empty_hashes(self, db):
        names = await db.get_contact_names_for_chats([], ["123@s.whatsapp.net"])
        assert names == {}

    @pytest.mark.asyncio
    async def test_empty_jids(self, db):
        names = await db.get_contact_names_for_chats(["hash1"], [])
        assert names == {}

    @pytest.mark.asyncio
    async def test_returns_contact_names(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            push_name="John Doe",
            text="Hello",
            timestamp=1000,
        )
        names = await db.get_contact_names_for_chats(
            ["hash1"], ["1234567890@s.whatsapp.net"]
        )
        assert ("hash1", "1234567890@s.whatsapp.net") in names
        assert names[("hash1", "1234567890@s.whatsapp.net")]["name"] == "John Doe"


class TestGetContactNamesForSenders:
    @pytest.mark.asyncio
    async def test_returns_sender_names(self, db):
        await db.save_tenant("hash1", "Test Tenant", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="9876543210@s.whatsapp.net",
            chat_jid="9876543210@s.whatsapp.net",
            push_name="Jane",
            text="Hi",
            timestamp=1000,
        )
        names = await db.get_contact_names_for_senders(
            ["hash1"], ["9876543210@s.whatsapp.net"]
        )
        assert ("hash1", "9876543210@s.whatsapp.net") in names
        assert names[("hash1", "9876543210@s.whatsapp.net")]["name"] == "Jane"


class TestQueryContactNames:
    @pytest.mark.asyncio
    async def test_query_multiple_hashes_and_jids(self, db):
        await db.save_tenant("hash1", "Tenant1", datetime.now(UTC), [])
        await db.save_tenant("hash2", "Tenant2", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="111@s.whatsapp.net",
            chat_jid="111@s.whatsapp.net",
            push_name="Alice",
            text="Hi",
            timestamp=1000,
        )
        await db.save_message(
            tenant_hash="hash2",
            message_id="msg2",
            from_jid="222@s.whatsapp.net",
            chat_jid="222@s.whatsapp.net",
            push_name="Bob",
            text="Hey",
            timestamp=1000,
        )
        result = await db._query_contact_names(
            ["hash1", "hash2"], ["111@s.whatsapp.net", "222@s.whatsapp.net"]
        )
        assert ("hash1", "111@s.whatsapp.net") in result
        assert ("hash2", "222@s.whatsapp.net") in result
        assert result[("hash1", "111@s.whatsapp.net")]["name"] == "Alice"
        assert result[("hash2", "222@s.whatsapp.net")]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_query_no_match(self, db):
        result = await db._query_contact_names(
            ["hash_nonexistent"], ["nonexistent@s.whatsapp.net"]
        )
        assert result == {}


class TestMarkMessageChatwootSynced:
    @pytest.mark.asyncio
    async def test_mark_synced(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        msg_id = await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="123@s.whatsapp.net",
            chat_jid="123@s.whatsapp.net",
            text="Hello",
            timestamp=1000,
        )
        assert msg_id is not None
        await db.mark_message_chatwoot_synced(msg_id)
        unsynced = await db.get_unsynced_messages_for_chatwoot("hash1", days_limit=7)
        assert len(unsynced) == 0


class TestGetUnsyncedMessagesForChatwoot:
    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, db):
        result = await db.get_unsynced_messages_for_chatwoot("hash1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_unsynced_messages(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="123@s.whatsapp.net",
            chat_jid="123@s.whatsapp.net",
            text="Hello",
            timestamp=1000,
        )
        result = await db.get_unsynced_messages_for_chatwoot("hash1")
        assert len(result) == 1
        assert result[0]["message_id"] == "msg1"

    @pytest.mark.asyncio
    async def test_respects_days_limit(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        msg_id = await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            text="Hello",
            timestamp=1000,
        )
        old_date = "2020-01-01T00:00:00"
        await db._pool.execute(
            "UPDATE messages SET created_at = ? WHERE id = ?",
            (old_date, msg_id),
        )
        await db._pool.commit()
        result = await db.get_unsynced_messages_for_chatwoot("hash1", days_limit=1)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_excludes_group_messages(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="user@s.whatsapp.net",
            chat_jid="group@g.us",
            text="Hello",
            timestamp=1000,
            is_group=True,
        )
        result = await db.get_unsynced_messages_for_chatwoot("hash1")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_respects_limit(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        for i in range(5):
            await db.save_message(
                tenant_hash="hash1",
                message_id=f"msg{i}",
                from_jid="123@s.whatsapp.net",
                chat_jid="123@s.whatsapp.net",
                text=f"Hello {i}",
                timestamp=1000 + i,
            )
        result = await db.get_unsynced_messages_for_chatwoot("hash1", limit=2)
        assert len(result) == 2


class TestUpdateMessageMediaUrl:
    @pytest.mark.asyncio
    async def test_update_media_url(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="123@s.whatsapp.net",
            chat_jid="123@s.whatsapp.net",
            text="Hello",
            timestamp=1000,
        )
        await db.update_message_media_url(
            tenant_hash="hash1",
            message_id="msg1",
            media_url="https://example.com/image.jpg",
        )
        msg = await db.get_message_by_id("hash1", "msg1")
        assert msg is not None
        assert msg["media_url"] == "https://example.com/image.jpg"

    @pytest.mark.asyncio
    async def test_update_media_url_nonexistent_message(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.update_message_media_url(
            tenant_hash="hash1",
            message_id="nonexistent",
            media_url="https://example.com/image.jpg",
        )


def _make_mock_pg_pool(mock_conn):
    mock_pool = AsyncMock()
    mock_pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    mock_pool.close = AsyncMock()
    return mock_pool


class TestPostgresPathsWithMocks:
    @pytest.mark.asyncio
    async def test_save_tenant_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        db._pool = _make_mock_pg_pool(mock_conn)

        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tenant_enabled_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        db._pool = _make_mock_pg_pool(mock_conn)

        await db.update_tenant_enabled("hash1", True)
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        assert "$1" in call_args[0]
        assert call_args[1] is True

    @pytest.mark.asyncio
    async def test_cleanup_old_data_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 0")
        db._pool = _make_mock_pg_pool(mock_conn)

        result = await db.cleanup_old_data(days=30)
        assert "webhook_attempts" in result
        assert "messages" in result
        assert "admin_sessions" in result

    @pytest.mark.asyncio
    async def test_mark_message_chatwoot_synced_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        db._pool = _make_mock_pg_pool(mock_conn)

        await db.mark_message_chatwoot_synced(42)
        mock_conn.execute.assert_called_once()
        assert "chatwoot_synced_at" in mock_conn.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_unsynced_messages_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        db._pool = _make_mock_pg_pool(mock_conn)

        result = await db.get_unsynced_messages_for_chatwoot("hash1", days_limit=3)
        assert result == []
        mock_conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_message_media_url_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        db._pool = _make_mock_pg_pool(mock_conn)

        await db.update_message_media_url(
            "hash1", "msg1", "https://example.com/img.jpg"
        )
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_contact_names_postgres(self):
        db = Database("postgresql://u:p@h/db", Path("/tmp"))
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "tenant_hash": "h1",
                    "chat_jid": "j1",
                    "name": "Alice",
                    "is_group": False,
                }
            ]
        )
        db._pool = _make_mock_pg_pool(mock_conn)

        result = await db._query_contact_names(["h1"], ["j1"])
        assert ("h1", "j1") in result
        assert result[("h1", "j1")]["name"] == "Alice"
