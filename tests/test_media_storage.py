import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime

from src.store.messages import StoredMessage, MessageStore


class TestStoredMessageMediaFields:
    def test_stored_message_stores_media_url(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Image",
            msg_type="image",
            timestamp=1234567890000,
            media_url="https://example.com/image.jpg",
        )
        assert msg.media_url == "https://example.com/image.jpg"

    def test_stored_message_stores_mimetype(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Video",
            msg_type="video",
            timestamp=1234567890000,
            mimetype="video/mp4",
        )
        assert msg.mimetype == "video/mp4"

    def test_stored_message_stores_filename(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Doc",
            msg_type="document",
            timestamp=1234567890000,
            filename="report.pdf",
        )
        assert msg.filename == "report.pdf"

    def test_stored_message_stores_coordinates(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            msg_type="location",
            timestamp=1234567890000,
            latitude=37.7749,
            longitude=-122.4194,
        )
        assert msg.latitude == 37.7749
        assert msg.longitude == -122.4194

    def test_stored_message_stores_location_details(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            msg_type="location",
            timestamp=1234567890000,
            location_name="San Francisco",
            location_address="123 Main St",
        )
        assert msg.location_name == "San Francisco"
        assert msg.location_address == "123 Main St"

    def test_stored_message_to_dict_includes_all_media_fields(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Full media message",
            msg_type="image",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/full.jpg",
            mimetype="image/jpeg",
            filename="photo.jpg",
            latitude=40.7128,
            longitude=-74.0060,
            location_name="NYC",
            location_address="New York",
            db_id=42,
        )

        result = msg.to_dict()

        assert result["id"] == "msg123"
        assert result["media_url"] == "https://example.com/full.jpg"
        assert result["mimetype"] == "image/jpeg"
        assert result["filename"] == "photo.jpg"
        assert result["latitude"] == 40.7128
        assert result["longitude"] == -74.0060
        assert result["location_name"] == "NYC"
        assert result["location_address"] == "New York"
        assert result["db_id"] == 42

    def test_stored_message_to_dict_handles_none_values(self):
        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Text only",
            msg_type="text",
            timestamp=1234567890000,
        )

        result = msg.to_dict()

        assert result["media_url"] is None
        assert result["mimetype"] is None
        assert result["filename"] is None
        assert result["latitude"] is None
        assert result["longitude"] is None
        assert result["location_name"] is None
        assert result["location_address"] is None


class TestMessageStoreWithMedia:
    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.save_message = AsyncMock(return_value=1)
        return db

    def test_add_stores_message_with_media(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Image",
            msg_type="image",
            timestamp=1234567890000,
            media_url="https://example.com/img.jpg",
            mimetype="image/jpeg",
        )

        store.add(msg)

        messages, total = store.list(limit=10)
        assert total == 1
        assert messages[0]["media_url"] == "https://example.com/img.jpg"
        assert messages[0]["mimetype"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_add_with_persist_saves_media_url(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Image",
            msg_type="image",
            timestamp=1234567890000,
            media_url="https://example.com/img.jpg",
        )

        db_id = await store.add_with_persist(msg)

        assert db_id == 1
        mock_db.save_message.assert_called_once()
        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["media_url"] == "https://example.com/img.jpg"

    @pytest.mark.asyncio
    async def test_add_with_persist_saves_mimetype(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Video",
            msg_type="video",
            timestamp=1234567890000,
            mimetype="video/mp4",
        )

        await store.add_with_persist(msg)

        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["mimetype"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_add_with_persist_saves_coordinates(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            msg_type="location",
            timestamp=1234567890000,
            latitude=51.5074,
            longitude=-0.1278,
        )

        await store.add_with_persist(msg)

        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["latitude"] == 51.5074
        assert call_kwargs["longitude"] == -0.1278

    @pytest.mark.asyncio
    async def test_add_with_persist_saves_location_details(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            msg_type="location",
            timestamp=1234567890000,
            location_name="London",
            location_address="UK",
        )

        await store.add_with_persist(msg)

        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["location_name"] == "London"
        assert call_kwargs["location_address"] == "UK"

    @pytest.mark.asyncio
    async def test_add_with_persist_handles_missing_media_fields(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Text only",
            msg_type="text",
            timestamp=1234567890000,
        )

        await store.add_with_persist(msg)

        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["media_url"] is None
        assert call_kwargs["mimetype"] is None
        assert call_kwargs["filename"] is None
        assert call_kwargs["latitude"] is None
        assert call_kwargs["longitude"] is None

    @pytest.mark.asyncio
    async def test_add_with_persist_saves_all_fields_together(self, mock_db):
        store = MessageStore(max_messages=100, tenant_hash="test_hash", db=mock_db)

        msg = StoredMessage(
            id="msg_full",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Full message",
            msg_type="image",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/full.jpg",
            mimetype="image/jpeg",
            filename="photo.jpg",
            latitude=48.8566,
            longitude=2.3522,
            location_name="Paris",
            location_address="France",
        )

        await store.add_with_persist(msg)

        call_kwargs = mock_db.save_message.call_args[1]
        assert call_kwargs["media_url"] == "https://example.com/full.jpg"
        assert call_kwargs["mimetype"] == "image/jpeg"
        assert call_kwargs["filename"] == "photo.jpg"
        assert call_kwargs["latitude"] == 48.8566
        assert call_kwargs["longitude"] == 2.3522
        assert call_kwargs["location_name"] == "Paris"
        assert call_kwargs["location_address"] == "France"


class TestStoredMessageDifferentTypes:
    def test_image_message_type(self):
        msg = StoredMessage(
            id="img1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Caption",
            msg_type="image",
            timestamp=1234567890000,
            media_url="https://example.com/img.jpg",
            mimetype="image/jpeg",
        )
        assert msg.type == "image"

    def test_video_message_type(self):
        msg = StoredMessage(
            id="vid1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="video",
            timestamp=1234567890000,
            media_url="https://example.com/vid.mp4",
            mimetype="video/mp4",
        )
        assert msg.type == "video"

    def test_audio_message_type(self):
        msg = StoredMessage(
            id="aud1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="audio",
            timestamp=1234567890000,
            media_url="https://example.com/aud.ogg",
            mimetype="audio/ogg",
        )
        assert msg.type == "audio"

    def test_document_message_type(self):
        msg = StoredMessage(
            id="doc1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="document",
            timestamp=1234567890000,
            media_url="https://example.com/doc.pdf",
            mimetype="application/pdf",
            filename="report.pdf",
        )
        assert msg.type == "document"

    def test_location_message_type(self):
        msg = StoredMessage(
            id="loc1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1234567890000,
            latitude=35.6762,
            longitude=139.6503,
            location_name="Tokyo",
        )
        assert msg.type == "location"

    def test_sticker_message_type(self):
        msg = StoredMessage(
            id="stk1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="sticker",
            timestamp=1234567890000,
            media_url="https://example.com/sticker.webp",
        )
        assert msg.type == "sticker"

    def test_contact_message_type(self):
        msg = StoredMessage(
            id="cnt1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="John Doe",
            msg_type="contact",
            timestamp=1234567890000,
        )
        assert msg.type == "contact"
