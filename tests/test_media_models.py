import pytest
from src.models.message import InboundMessage, MessageType


class TestInboundMessageMediaFields:
    def test_inbound_message_accepts_media_url(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Check this image",
            type=MessageType.IMAGE,
            timestamp=1234567890000,
            media_url="https://example.com/image.jpg",
        )
        assert msg.media_url == "https://example.com/image.jpg"

    def test_inbound_message_accepts_mimetype(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Video",
            type=MessageType.VIDEO,
            timestamp=1234567890000,
            mimetype="video/mp4",
        )
        assert msg.mimetype == "video/mp4"

    def test_inbound_message_accepts_filename(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            type=MessageType.DOCUMENT,
            timestamp=1234567890000,
            filename="report.pdf",
        )
        assert msg.filename == "report.pdf"

    def test_inbound_message_accepts_latitude_longitude(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            type=MessageType.LOCATION,
            timestamp=1234567890000,
            latitude=37.7749,
            longitude=-122.4194,
        )
        assert msg.latitude == 37.7749
        assert msg.longitude == -122.4194

    def test_inbound_message_accepts_location_name_address(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Location",
            type=MessageType.LOCATION,
            timestamp=1234567890000,
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco",
            location_address="123 Main St, SF",
        )
        assert msg.location_name == "San Francisco"
        assert msg.location_address == "123 Main St, SF"

    def test_inbound_message_defaults_none_for_media_fields(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Hello",
            type=MessageType.TEXT,
            timestamp=1234567890000,
        )
        assert msg.media_url is None
        assert msg.mimetype is None
        assert msg.filename is None
        assert msg.latitude is None
        assert msg.longitude is None
        assert msg.location_name is None
        assert msg.location_address is None

    def test_inbound_message_with_all_media_fields_serializes_correctly(self):
        msg = InboundMessage(
            id="msg123",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            is_group=False,
            push_name="Sender",
            text="Check this",
            type=MessageType.IMAGE,
            timestamp=1234567890000,
            media_url="https://example.com/image.jpg",
            mimetype="image/jpeg",
            filename=None,
            latitude=None,
            longitude=None,
            location_name=None,
            location_address=None,
        )
        data = msg.model_dump()
        assert data["media_url"] == "https://example.com/image.jpg"
        assert data["mimetype"] == "image/jpeg"
        assert data["type"] == MessageType.IMAGE

    def test_inbound_message_with_alias_from_field(self):
        msg = InboundMessage(
            id="msg123",
            **{"from": "sender@s.whatsapp.net"},
            chat_jid="sender@s.whatsapp.net",
            text="Hello",
            type=MessageType.TEXT,
            timestamp=1234567890000,
        )
        assert msg.from_jid == "sender@s.whatsapp.net"


class TestMessageTypeEnum:
    def test_message_type_values(self):
        assert MessageType.TEXT == "text"
        assert MessageType.IMAGE == "image"
        assert MessageType.VIDEO == "video"
        assert MessageType.AUDIO == "audio"
        assert MessageType.DOCUMENT == "document"
        assert MessageType.STICKER == "sticker"
        assert MessageType.LOCATION == "location"
        assert MessageType.CONTACT == "contact"
        assert MessageType.EMPTY == "empty"
        assert MessageType.UNKNOWN == "unknown"

    def test_message_type_from_string(self):
        assert MessageType("image") == MessageType.IMAGE
        assert MessageType("video") == MessageType.VIDEO
        assert MessageType("location") == MessageType.LOCATION
