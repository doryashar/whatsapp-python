import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from src.store.database import Database


class TestSaveMessageWithMedia:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_save_image_message_with_url_and_mimetype(self, db):
        tenant_hash = "test_hash_image"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_image_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Check this image",
            msg_type="image",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/image.jpg",
            mimetype="image/jpeg",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_image_1")
        assert msg is not None
        assert msg["media_url"] == "https://example.com/image.jpg"
        assert msg["mimetype"] == "image/jpeg"
        assert msg["msg_type"] == "image"

    @pytest.mark.asyncio
    async def test_save_video_message_with_url(self, db):
        tenant_hash = "test_hash_video"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_video_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Video caption",
            msg_type="video",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/video.mp4",
            mimetype="video/mp4",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_video_1")
        assert msg["media_url"] == "https://example.com/video.mp4"
        assert msg["mimetype"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_save_audio_message(self, db):
        tenant_hash = "test_hash_audio"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_audio_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="audio",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/audio.ogg",
            mimetype="audio/ogg",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_audio_1")
        assert msg["media_url"] == "https://example.com/audio.ogg"
        assert msg["mimetype"] == "audio/ogg"

    @pytest.mark.asyncio
    async def test_save_document_with_filename(self, db):
        tenant_hash = "test_hash_doc"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_doc_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="document",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/report.pdf",
            mimetype="application/pdf",
            filename="Annual Report 2024.pdf",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_doc_1")
        assert msg["media_url"] == "https://example.com/report.pdf"
        assert msg["filename"] == "Annual Report 2024.pdf"
        assert msg["mimetype"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_save_location_with_coordinates(self, db):
        tenant_hash = "test_hash_location"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_location_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1234567890000,
            direction="inbound",
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco",
            location_address="123 Main St, San Francisco, CA",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_location_1")
        assert msg["latitude"] == 37.7749
        assert msg["longitude"] == -122.4194
        assert msg["location_name"] == "San Francisco"
        assert msg["location_address"] == "123 Main St, San Francisco, CA"

    @pytest.mark.asyncio
    async def test_save_message_with_all_media_fields(self, db):
        tenant_hash = "test_hash_all"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_all_fields",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Caption text",
            msg_type="image",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/full.jpg",
            mimetype="image/jpeg",
            filename="photo.jpg",
            latitude=40.7128,
            longitude=-74.0060,
            location_name="New York",
            location_address="NYC",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_all_fields")
        assert msg["media_url"] == "https://example.com/full.jpg"
        assert msg["mimetype"] == "image/jpeg"
        assert msg["filename"] == "photo.jpg"
        assert msg["latitude"] == 40.7128
        assert msg["longitude"] == -74.0060
        assert msg["location_name"] == "New York"
        assert msg["location_address"] == "NYC"

    @pytest.mark.asyncio
    async def test_save_message_without_media_fields_stores_none(self, db):
        tenant_hash = "test_hash_text"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        db_id = await db.save_message(
            tenant_hash=tenant_hash,
            message_id="msg_text_only",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Just text",
            msg_type="text",
            timestamp=1234567890000,
            direction="inbound",
        )

        assert db_id is not None

        msg = await db.get_message_by_id(tenant_hash, "msg_text_only")
        assert msg["media_url"] is None
        assert msg["mimetype"] is None
        assert msg["filename"] is None
        assert msg["latitude"] is None
        assert msg["longitude"] is None
        assert msg["location_name"] is None
        assert msg["location_address"] is None


class TestListMessagesWithMedia:
    @pytest.fixture
    async def db_with_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()

            tenant_hash = "test_list_hash"
            await database.save_tenant(
                tenant_hash, "test_tenant", datetime.now(UTC), []
            )

            await database.save_message(
                tenant_hash=tenant_hash,
                message_id="msg_image",
                from_jid="sender@s.whatsapp.net",
                chat_jid="sender@s.whatsapp.net",
                text="Image caption",
                msg_type="image",
                timestamp=1234567890000,
                direction="inbound",
                media_url="https://example.com/img.jpg",
                mimetype="image/jpeg",
            )

            await database.save_message(
                tenant_hash=tenant_hash,
                message_id="msg_location",
                from_jid="sender@s.whatsapp.net",
                chat_jid="sender@s.whatsapp.net",
                text="",
                msg_type="location",
                timestamp=1234567891000,
                direction="inbound",
                latitude=51.5074,
                longitude=-0.1278,
                location_name="London",
            )

            await database.save_message(
                tenant_hash=tenant_hash,
                message_id="msg_text",
                from_jid="sender@s.whatsapp.net",
                chat_jid="sender@s.whatsapp.net",
                text="Plain text",
                msg_type="text",
                timestamp=1234567892000,
                direction="outbound",
            )

            yield database, tenant_hash
            await database.close()

    @pytest.mark.asyncio
    async def test_list_messages_returns_media_url(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        image_msg = next((m for m in messages if m["message_id"] == "msg_image"), None)
        assert image_msg is not None
        assert image_msg["media_url"] == "https://example.com/img.jpg"

    @pytest.mark.asyncio
    async def test_list_messages_returns_mimetype(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        image_msg = next((m for m in messages if m["message_id"] == "msg_image"), None)
        assert image_msg is not None
        assert image_msg["mimetype"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_list_messages_returns_filename(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        assert total == 3

    @pytest.mark.asyncio
    async def test_list_messages_returns_coordinates(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        location_msg = next(
            (m for m in messages if m["message_id"] == "msg_location"), None
        )
        assert location_msg is not None
        assert location_msg["latitude"] == 51.5074
        assert location_msg["longitude"] == -0.1278

    @pytest.mark.asyncio
    async def test_list_messages_returns_location_details(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        location_msg = next(
            (m for m in messages if m["message_id"] == "msg_location"), None
        )
        assert location_msg is not None
        assert location_msg["location_name"] == "London"

    @pytest.mark.asyncio
    async def test_list_messages_handles_null_media_fields(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        text_msg = next((m for m in messages if m["message_id"] == "msg_text"), None)
        assert text_msg is not None
        assert text_msg["media_url"] is None
        assert text_msg["mimetype"] is None
        assert text_msg["latitude"] is None
        assert text_msg["longitude"] is None

    @pytest.mark.asyncio
    async def test_list_messages_with_filter(self, db_with_messages):
        db, tenant_hash = db_with_messages
        messages, total = await db.list_messages(
            tenant_hash=tenant_hash, direction="inbound", limit=10
        )

        assert total == 2
        assert all(m["direction"] == "inbound" for m in messages)


class TestDatabaseMigrations:
    @pytest.mark.asyncio
    async def test_new_columns_added_on_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db = Database("", data_dir)
            await db.connect()

            async with db._pool.execute("PRAGMA table_info(messages)") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

            assert "media_url" in column_names
            assert "mimetype" in column_names
            assert "filename" in column_names
            assert "latitude" in column_names
            assert "longitude" in column_names
            assert "location_name" in column_names
            assert "location_address" in column_names

            await db.close()

    @pytest.mark.asyncio
    async def test_existing_data_migrated_successfully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db = Database("", data_dir)
            await db.connect()

            tenant_hash = "migration_test"
            await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

            await db.save_message(
                tenant_hash=tenant_hash,
                message_id="old_msg",
                from_jid="test@s.whatsapp.net",
                chat_jid="test@s.whatsapp.net",
                text="Old message",
                msg_type="text",
                timestamp=1000000000000,
                direction="inbound",
            )

            msg = await db.get_message_by_id(tenant_hash, "old_msg")
            assert msg is not None
            assert msg["text"] == "Old message"

            await db.close()
