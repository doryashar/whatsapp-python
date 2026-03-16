import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from src.store.database import Database
from src.store.messages import StoredMessage, MessageStore


class TestBackwardCompatibility:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_old_messages_list_correctly(self, db):
        tenant_hash = "backward_compat"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="old_msg_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Old text message",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="old_msg_2",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Another old message",
            msg_type="text",
            timestamp=1700000001000,
            direction="outbound",
        )

        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)
        assert total == 2

        for msg in messages:
            assert msg["media_url"] is None
            assert msg["mimetype"] is None
            assert msg["filename"] is None
            assert msg["latitude"] is None
            assert msg["longitude"] is None

    @pytest.mark.asyncio
    async def test_mixed_old_and_new_messages(self, db):
        tenant_hash = "mixed_compat"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="old_text",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Old text",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="new_image",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="New image",
            msg_type="image",
            timestamp=1700000001000,
            direction="inbound",
            media_url="https://example.com/new.jpg",
            mimetype="image/jpeg",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="old_text_2",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Another old",
            msg_type="text",
            timestamp=1700000002000,
            direction="inbound",
        )

        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)
        assert total == 3

        old_msgs = [m for m in messages if m["message_id"].startswith("old_")]
        for msg in old_msgs:
            assert msg["media_url"] is None

        new_msg = next(m for m in messages if m["message_id"] == "new_image")
        assert new_msg["media_url"] == "https://example.com/new.jpg"

    @pytest.mark.asyncio
    async def test_get_message_by_id_old_format(self, db):
        tenant_hash = "get_old_format"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="get_old_msg",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Old message",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        msg = await db.get_message_by_id(tenant_hash, "get_old_msg")
        assert msg is not None
        assert msg["text"] == "Old message"
        assert msg["media_url"] is None
        assert msg["mimetype"] is None
        assert msg["filename"] is None
        assert msg["latitude"] is None
        assert msg["longitude"] is None
        assert msg["location_name"] is None
        assert msg["location_address"] is None


class TestStoredMessageBackwardCompat:
    def test_stored_message_without_media_fields(self):
        msg = StoredMessage(
            id="no_media",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Text only",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        assert msg.media_url is None
        assert msg.mimetype is None
        assert msg.filename is None
        assert msg.latitude is None
        assert msg.longitude is None
        assert msg.location_name is None
        assert msg.location_address is None

    def test_stored_message_to_dict_backward_compat(self):
        msg = StoredMessage(
            id="compat_dict",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Test",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        d = msg.to_dict()

        assert "media_url" in d
        assert d["media_url"] is None
        assert "mimetype" in d
        assert d["mimetype"] is None
        assert "latitude" in d
        assert d["latitude"] is None

    def test_stored_message_partial_media_fields(self):
        msg = StoredMessage(
            id="partial",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Partial",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/partial.jpg",
        )

        assert msg.media_url == "https://example.com/partial.jpg"
        assert msg.mimetype is None
        assert msg.filename is None


class TestMessageStoreBackwardCompat:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_message_store_old_style_add(self, db):
        tenant_hash = "store_compat"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        store = MessageStore(max_messages=100, tenant_hash=tenant_hash, db=db)

        msg = StoredMessage(
            id="store_old",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Old style",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        await store.add_with_persist(msg)

        retrieved = await db.get_message_by_id(tenant_hash, "store_old")
        assert retrieved is not None
        assert retrieved["text"] == "Old style"

    @pytest.mark.asyncio
    async def test_message_store_new_style_add(self, db):
        tenant_hash = "store_new"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        store = MessageStore(max_messages=100, tenant_hash=tenant_hash, db=db)

        msg = StoredMessage(
            id="store_new",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="New style",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/new.jpg",
            mimetype="image/jpeg",
        )

        await store.add_with_persist(msg)

        retrieved = await db.get_message_by_id(tenant_hash, "store_new")
        assert retrieved["media_url"] == "https://example.com/new.jpg"


class TestDatabaseSchemaMigration:
    @pytest.mark.asyncio
    async def test_fresh_database_has_media_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db = Database("", data_dir)
            await db.connect()

            async with db._pool.execute("PRAGMA table_info(messages)") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

            required_columns = [
                "media_url",
                "mimetype",
                "filename",
                "latitude",
                "longitude",
                "location_name",
                "location_address",
            ]

            for col in required_columns:
                assert col in column_names, f"Missing column: {col}"

            await db.close()

    @pytest.mark.asyncio
    async def test_existing_data_after_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db = Database("", data_dir)
            await db.connect()

            tenant_hash = "migration_test"
            await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

            await db.save_message(
                tenant_hash=tenant_hash,
                message_id="pre_migration",
                from_jid="test@s.whatsapp.net",
                chat_jid="test@s.whatsapp.net",
                text="Pre-migration message",
                msg_type="text",
                timestamp=1000000000000,
                direction="inbound",
            )

            msg = await db.get_message_by_id(tenant_hash, "pre_migration")
            assert msg is not None
            assert msg["text"] == "Pre-migration message"

            assert msg["media_url"] is None
            assert msg["mimetype"] is None
            assert msg["filename"] is None
            assert msg["latitude"] is None
            assert msg["longitude"] is None
            assert msg["location_name"] is None
            assert msg["location_address"] is None

            await db.close()


class TestApiBackwardCompatibility:
    def test_message_dict_structure_unchanged(self):
        msg = StoredMessage(
            id="api_test",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            push_name="Sender",
            text="API test",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
        )

        d = msg.to_dict()

        assert "id" in d
        assert "from_jid" in d
        assert "chat_jid" in d
        assert "text" in d
        assert "type" in d
        assert "timestamp" in d
        assert "direction" in d

    def test_new_fields_appended_not_inserted(self):
        msg = StoredMessage(
            id="field_order",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Field order test",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/test.jpg",
        )

        d = msg.to_dict()
        keys = list(d.keys())

        id_idx = keys.index("id")
        text_idx = keys.index("text")
        type_idx = keys.index("type")

        assert id_idx < text_idx < type_idx
