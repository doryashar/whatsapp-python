import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, UTC

from src.main import handle_bridge_event
from src.store.messages import StoredMessage
from src.store.database import Database
from src.tenant import Tenant
from src.store.messages import MessageStore


class TestBridgeEventMediaFields:
    @pytest.fixture
    async def setup_tenant(self, tmp_path):
        db = Database("", tmp_path)
        await db.connect()

        tenant_hash = "test_media_bridge_hash"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        tenant = Tenant(
            api_key_hash=tenant_hash,
            name="test_tenant",
            message_store=MessageStore(
                max_messages=1000, tenant_hash=tenant_hash, db=db
            ),
        )

        yield {"db": db, "tenant": tenant, "tenant_hash": tenant_hash}

        await db.close()

    @pytest.mark.asyncio
    async def test_message_event_with_image_media_url(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant = setup["tenant"]
        tenant_hash = setup["tenant_hash"]

        params = {
            "id": "img_msg_123",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "push_name": "Sender",
            "text": "Check this image",
            "type": "image",
            "timestamp": 1234567890000,
            "media_url": "https://example.com/image.jpg",
            "mimetype": "image/jpeg",
        }

        msg = StoredMessage(
            id=params.get("id"),
            from_jid=params.get("from"),
            chat_jid=params.get("chat_jid"),
            is_group=params.get("is_group", False),
            push_name=params.get("push_name"),
            text=params.get("text", ""),
            msg_type=params.get("type", "text"),
            timestamp=params.get("timestamp", 0),
            direction="inbound",
            media_url=params.get("media_url"),
            mimetype=params.get("mimetype"),
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            media_url=msg.media_url,
            mimetype=msg.mimetype,
        )

        saved = await db.get_message_by_id(tenant_hash, "img_msg_123")
        assert saved is not None
        assert saved["media_url"] == "https://example.com/image.jpg"
        assert saved["mimetype"] == "image/jpeg"
        assert saved["msg_type"] == "image"

    @pytest.mark.asyncio
    async def test_message_event_with_video_fields(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant_hash = setup["tenant_hash"]

        msg = StoredMessage(
            id="video_msg_456",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            push_name="Sender",
            text="Video caption",
            msg_type="video",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/video.mp4",
            mimetype="video/mp4",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            media_url=msg.media_url,
            mimetype=msg.mimetype,
        )

        saved = await db.get_message_by_id(tenant_hash, "video_msg_456")
        assert saved["media_url"] == "https://example.com/video.mp4"
        assert saved["mimetype"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_message_event_with_audio_fields(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant_hash = setup["tenant_hash"]

        msg = StoredMessage(
            id="audio_msg_789",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            text="",
            msg_type="audio",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/audio.ogg",
            mimetype="audio/ogg",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            media_url=msg.media_url,
            mimetype=msg.mimetype,
        )

        saved = await db.get_message_by_id(tenant_hash, "audio_msg_789")
        assert saved["media_url"] == "https://example.com/audio.ogg"
        assert saved["mimetype"] == "audio/ogg"

    @pytest.mark.asyncio
    async def test_message_event_with_document_fields(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant_hash = setup["tenant_hash"]

        msg = StoredMessage(
            id="doc_msg_abc",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            text="",
            msg_type="document",
            timestamp=1234567890000,
            direction="inbound",
            media_url="https://example.com/report.pdf",
            mimetype="application/pdf",
            filename="Report 2024.pdf",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            media_url=msg.media_url,
            mimetype=msg.mimetype,
            filename=msg.filename,
        )

        saved = await db.get_message_by_id(tenant_hash, "doc_msg_abc")
        assert saved["media_url"] == "https://example.com/report.pdf"
        assert saved["mimetype"] == "application/pdf"
        assert saved["filename"] == "Report 2024.pdf"

    @pytest.mark.asyncio
    async def test_message_event_with_location_fields(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant_hash = setup["tenant_hash"]

        msg = StoredMessage(
            id="loc_msg_def",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            text="",
            msg_type="location",
            timestamp=1234567890000,
            direction="inbound",
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco",
            location_address="123 Main St",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            latitude=msg.latitude,
            longitude=msg.longitude,
            location_name=msg.location_name,
            location_address=msg.location_address,
        )

        saved = await db.get_message_by_id(tenant_hash, "loc_msg_def")
        assert saved["latitude"] == 37.7749
        assert saved["longitude"] == -122.4194
        assert saved["location_name"] == "San Francisco"
        assert saved["location_address"] == "123 Main St"

    @pytest.mark.asyncio
    async def test_outbound_message_with_media_fields(self, setup_tenant):
        setup = setup_tenant
        db = setup["db"]
        tenant_hash = setup["tenant_hash"]

        msg = StoredMessage(
            id="out_img_123",
            from_jid="me@s.whatsapp.net",
            chat_jid="recipient@s.whatsapp.net",
            is_group=False,
            text="Sent image",
            msg_type="image",
            timestamp=1234567890000,
            direction="outbound",
            media_url="https://example.com/sent.jpg",
            mimetype="image/jpeg",
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            text=msg.text,
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
            media_url=msg.media_url,
            mimetype=msg.mimetype,
        )

        saved = await db.get_message_by_id(tenant_hash, "out_img_123")
        assert saved["direction"] == "outbound"
        assert saved["media_url"] == "https://example.com/sent.jpg"


class TestBridgeEventDataMapping:
    def test_image_message_params_from_bridge(self):
        bridge_params = {
            "id": "msg123",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "push_name": "John",
            "text": "Check this out",
            "type": "image",
            "timestamp": 1700000000000,
            "media_url": "https://mmg.whatsapp.net/image.jpg",
            "mimetype": "image/jpeg",
            "media_key": "abc123",
        }

        assert bridge_params["type"] == "image"
        assert bridge_params["media_url"] is not None
        assert bridge_params["mimetype"] == "image/jpeg"

    def test_location_message_params_from_bridge(self):
        bridge_params = {
            "id": "msg456",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "push_name": "Jane",
            "text": "https://maps.google.com/?q=37.7749,-122.4194",
            "type": "location",
            "timestamp": 1700000000000,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "location_name": "San Francisco",
            "location_address": "California St",
        }

        assert bridge_params["type"] == "location"
        assert bridge_params["latitude"] == 37.7749
        assert bridge_params["longitude"] == -122.4194
        assert bridge_params["location_name"] == "San Francisco"

    def test_document_message_params_from_bridge(self):
        bridge_params = {
            "id": "msg789",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "text": "",
            "type": "document",
            "timestamp": 1700000000000,
            "media_url": "https://mmg.whatsapp.net/doc.pdf",
            "mimetype": "application/pdf",
            "filename": "Report_Q4_2024.pdf",
        }

        assert bridge_params["type"] == "document"
        assert bridge_params["filename"] == "Report_Q4_2024.pdf"
        assert bridge_params["mimetype"] == "application/pdf"

    def test_video_message_params_from_bridge(self):
        bridge_params = {
            "id": "msg_vid",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "text": "Funny video",
            "type": "video",
            "timestamp": 1700000000000,
            "media_url": "https://mmg.whatsapp.net/video.mp4",
            "mimetype": "video/mp4",
        }

        assert bridge_params["type"] == "video"
        assert bridge_params["media_url"] is not None
        assert "video" in bridge_params["mimetype"]

    def test_audio_message_params_from_bridge(self):
        bridge_params = {
            "id": "msg_audio",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "text": "",
            "type": "audio",
            "timestamp": 1700000000000,
            "media_url": "https://mmg.whatsapp.net/audio.ogg",
            "mimetype": "audio/ogg; codecs=opus",
        }

        assert bridge_params["type"] == "audio"
        assert bridge_params["media_url"] is not None
        assert "audio" in bridge_params["mimetype"]

    def test_text_message_params_no_media(self):
        bridge_params = {
            "id": "msg_text",
            "from": "sender@s.whatsapp.net",
            "chat_jid": "sender@s.whatsapp.net",
            "is_group": False,
            "push_name": "Bob",
            "text": "Hello world",
            "type": "text",
            "timestamp": 1700000000000,
        }

        assert bridge_params["type"] == "text"
        assert (
            "media_url" not in bridge_params or bridge_params.get("media_url") is None
        )


class TestStoredMessageMediaFields:
    def test_stored_message_with_media_url(self):
        msg = StoredMessage(
            id="test_id",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/img.jpg",
        )
        assert msg.media_url == "https://example.com/img.jpg"

    def test_stored_message_with_all_location_fields(self):
        msg = StoredMessage(
            id="test_loc",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            msg_type="location",
            timestamp=1700000000000,
            direction="inbound",
            latitude=51.5074,
            longitude=-0.1278,
            location_name="London",
            location_address="UK",
        )
        assert msg.latitude == 51.5074
        assert msg.longitude == -0.1278
        assert msg.location_name == "London"
        assert msg.location_address == "UK"

    def test_stored_message_to_dict_includes_media_fields(self):
        msg = StoredMessage(
            id="test_dict",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Caption",
            msg_type="video",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/video.mp4",
            mimetype="video/mp4",
            filename="video.mp4",
        )
        d = msg.to_dict()
        assert d["media_url"] == "https://example.com/video.mp4"
        assert d["mimetype"] == "video/mp4"
        assert d["filename"] == "video.mp4"

    def test_stored_message_defaults_none_for_media(self):
        msg = StoredMessage(
            id="test_none",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Plain text",
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
