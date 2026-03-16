import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from src.store.database import Database
from src.store.messages import StoredMessage
from src.models.message import InboundMessage, MessageType


class TestMissingMediaUrl:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_image_without_url_still_saved(self, db):
        tenant_hash = "no_url_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="img_no_url",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Image caption",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url=None,
            mimetype="image/jpeg",
        )

        msg = await db.get_message_by_id(tenant_hash, "img_no_url")
        assert msg is not None
        assert msg["msg_type"] == "image"
        assert msg["media_url"] is None

    @pytest.mark.asyncio
    async def test_video_without_url_handled(self, db):
        tenant_hash = "video_no_url"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="vid_no_url",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Video",
            msg_type="video",
            timestamp=1700000000000,
            direction="inbound",
        )

        msg = await db.get_message_by_id(tenant_hash, "vid_no_url")
        assert msg["msg_type"] == "video"

    @pytest.mark.asyncio
    async def test_location_without_name_saved(self, db):
        tenant_hash = "loc_no_name"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="loc_no_name",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=0.0,
            longitude=0.0,
            location_name=None,
            location_address=None,
        )

        msg = await db.get_message_by_id(tenant_hash, "loc_no_name")
        assert msg["latitude"] == 0.0
        assert msg["longitude"] == 0.0
        assert msg["location_name"] is None


class TestInvalidMimetypes:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_unknown_mimetype_saved(self, db):
        tenant_hash = "unknown_mime"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="unknown_mime",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="document",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/file.xyz",
            mimetype="application/x-unknown-format",
        )

        msg = await db.get_message_by_id(tenant_hash, "unknown_mime")
        assert msg["mimetype"] == "application/x-unknown-format"

    @pytest.mark.asyncio
    async def test_empty_mimetype_saved(self, db):
        tenant_hash = "empty_mime"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="empty_mime",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="audio",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/audio.bin",
            mimetype="",
        )

        msg = await db.get_message_by_id(tenant_hash, "empty_mime")
        assert msg["mimetype"] == ""

    @pytest.mark.asyncio
    async def test_none_mimetype_saved_as_none(self, db):
        tenant_hash = "none_mime"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="none_mime",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/img.bin",
            mimetype=None,
        )

        msg = await db.get_message_by_id(tenant_hash, "none_mime")
        assert msg["mimetype"] is None


class TestLongFilenamesAndUrls:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_very_long_filename(self, db):
        tenant_hash = "long_filename"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        long_filename = "A" * 500 + ".pdf"

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="long_fname",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="document",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/file.pdf",
            filename=long_filename,
        )

        msg = await db.get_message_by_id(tenant_hash, "long_fname")
        assert msg["filename"] == long_filename
        assert len(msg["filename"]) == 504

    @pytest.mark.asyncio
    async def test_very_long_url(self, db):
        tenant_hash = "long_url"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        long_url = "https://example.com/" + "path/" * 100 + "file.jpg"

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="long_url",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url=long_url,
        )

        msg = await db.get_message_by_id(tenant_hash, "long_url")
        assert msg["media_url"] == long_url


class TestSpecialCharacters:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_filename_with_unicode(self, db):
        tenant_hash = "unicode_filename"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        unicode_filename = "文档_مستند_документ.pdf"

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="unicode_fname",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="document",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/file.pdf",
            filename=unicode_filename,
        )

        msg = await db.get_message_by_id(tenant_hash, "unicode_fname")
        assert msg["filename"] == unicode_filename

    @pytest.mark.asyncio
    async def test_location_name_with_special_chars(self, db):
        tenant_hash = "special_location"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        location_name = "Café de l'Île & Co. <Main Branch>"

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="special_loc",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=48.8566,
            longitude=2.3522,
            location_name=location_name,
        )

        msg = await db.get_message_by_id(tenant_hash, "special_loc")
        assert msg["location_name"] == location_name

    @pytest.mark.asyncio
    async def test_caption_with_emoji(self, db):
        tenant_hash = "emoji_caption"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        caption = "Hello 👋 World 🌍 Emoji 🎉"

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="emoji_caption",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text=caption,
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/emoji.jpg",
        )

        msg = await db.get_message_by_id(tenant_hash, "emoji_caption")
        assert msg["text"] == caption


class TestBoundaryCoordinates:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_extreme_latitude_positive(self, db):
        tenant_hash = "extreme_lat"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="extreme_lat",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=89.999999,
            longitude=0.0,
        )

        msg = await db.get_message_by_id(tenant_hash, "extreme_lat")
        assert msg["latitude"] == 89.999999

    @pytest.mark.asyncio
    async def test_extreme_latitude_negative(self, db):
        tenant_hash = "extreme_lat_neg"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="extreme_lat_neg",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=-89.999999,
            longitude=0.0,
        )

        msg = await db.get_message_by_id(tenant_hash, "extreme_lat_neg")
        assert msg["latitude"] == -89.999999

    @pytest.mark.asyncio
    async def test_extreme_longitude(self, db):
        tenant_hash = "extreme_long"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="extreme_long",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=0.0,
            longitude=179.999999,
        )

        msg = await db.get_message_by_id(tenant_hash, "extreme_long")
        assert msg["longitude"] == 179.999999


class TestNullAndEmptyValues:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_all_media_fields_null(self, db):
        tenant_hash = "all_null"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="all_null",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Text only",
            msg_type="text",
            timestamp=1700000000000,
            direction="inbound",
            media_url=None,
            mimetype=None,
            filename=None,
            latitude=None,
            longitude=None,
            location_name=None,
            location_address=None,
        )

        msg = await db.get_message_by_id(tenant_hash, "all_null")
        assert msg["media_url"] is None
        assert msg["mimetype"] is None
        assert msg["filename"] is None
        assert msg["latitude"] is None
        assert msg["longitude"] is None
        assert msg["location_name"] is None
        assert msg["location_address"] is None

    @pytest.mark.asyncio
    async def test_empty_string_vs_null_distinction(self, db):
        tenant_hash = "empty_vs_null"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="empty_loc_name",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=0.0,
            longitude=0.0,
            location_name="",
            location_address=None,
        )

        msg = await db.get_message_by_id(tenant_hash, "empty_loc_name")
        assert msg["location_name"] == ""
        assert msg["location_address"] is None


class TestUnknownMessageTypes:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_unknown_type_with_media_url(self, db):
        tenant_hash = "unknown_type"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="unknown_type",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="unknown",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/unknown.bin",
        )

        msg = await db.get_message_by_id(tenant_hash, "unknown_type")
        assert msg["msg_type"] == "unknown"
        assert msg["media_url"] == "https://example.com/unknown.bin"

    @pytest.mark.asyncio
    async def test_custom_type_preserved(self, db):
        tenant_hash = "custom_type"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="custom_type",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="poll",
            timestamp=1700000000000,
            direction="inbound",
        )

        msg = await db.get_message_by_id(tenant_hash, "custom_type")
        assert msg["msg_type"] == "poll"
