import pytest
from pydantic import ValidationError
from src.models.message import SendMessageRequest, InboundMessage, MessageType
from src.models.group import SendStatusRequest


class TestSendMessageRequest:
    def test_valid_text_message(self):
        req = SendMessageRequest(to="1234567890", text="Hello")
        assert req.to == "1234567890"
        assert req.text == "Hello"

    def test_to_required(self):
        with pytest.raises(ValidationError):
            SendMessageRequest(text="Hello")

    def test_text_required(self):
        with pytest.raises(ValidationError):
            SendMessageRequest(to="1234567890")

    def test_with_media_url(self):
        req = SendMessageRequest(
            to="1234567890", text="Hello", media_url="https://example.com/img.jpg"
        )
        assert req.media_url == "https://example.com/img.jpg"


class TestSendStatusRequest:
    def test_valid_status_text(self):
        req = SendStatusRequest(type="text", content="Hello world", all_contacts=True)
        assert req.type == "text"
        assert req.content == "Hello world"

    def test_valid_status_image(self):
        req = SendStatusRequest(
            type="image", content="https://example.com/img.jpg", all_contacts=True
        )
        assert req.type == "image"

    def test_valid_status_video(self):
        req = SendStatusRequest(
            type="video", content="https://example.com/vid.mp4", all_contacts=True
        )
        assert req.type == "video"

    def test_with_status_jid_list(self):
        req = SendStatusRequest(
            type="text", content="hello", status_jid_list=["123@s.whatsapp.net"]
        )
        assert req.status_jid_list == ["123@s.whatsapp.net"]
        assert req.all_contacts is False

    def test_with_all_optional_fields(self):
        req = SendStatusRequest(
            type="image",
            content="https://example.com/img.jpg",
            caption="My photo",
            background_color="#FF0000",
            font=2,
            all_contacts=True,
        )
        assert req.caption == "My photo"
        assert req.background_color == "#FF0000"
        assert req.font == 2

    def test_type_required(self):
        with pytest.raises(ValidationError):
            SendStatusRequest(content="hello", all_contacts=True)

    def test_content_required(self):
        with pytest.raises(ValidationError):
            SendStatusRequest(type="text", all_contacts=True)

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            SendStatusRequest(type="audio", content="data", all_contacts=True)

    def test_cannot_specify_both_recipients(self):
        with pytest.raises(ValidationError):
            SendStatusRequest(
                type="text",
                content="hello",
                all_contacts=True,
                status_jid_list=["123@s.whatsapp.net"],
            )

    def test_must_specify_recipients(self):
        with pytest.raises(ValidationError):
            SendStatusRequest(type="text", content="hello")


class TestInboundMessage:
    def test_minimal_message(self):
        msg = InboundMessage(
            id="msg123",
            **{"from": "123@s.whatsapp.net"},
            chat_jid="123@s.whatsapp.net",
            text="Hello",
            timestamp=1234567890,
        )
        assert msg.id == "msg123"
        assert msg.text == "Hello"
        assert msg.is_group is False

    def test_group_message(self):
        msg = InboundMessage(
            id="msg789",
            **{"from": "456@s.whatsapp.net"},
            chat_jid="group@g.us",
            is_group=True,
            text="Hi",
            timestamp=1234567890,
        )
        assert msg.is_group is True

    def test_media_message(self):
        msg = InboundMessage(
            id="media1",
            **{"from": "123@s.whatsapp.net"},
            chat_jid="123@s.whatsapp.net",
            text="",
            type=MessageType.IMAGE,
            timestamp=1234567890,
            media_url="https://example.com/img.jpg",
            mimetype="image/jpeg",
            filename="photo.jpg",
        )
        assert msg.type == MessageType.IMAGE
        assert msg.mimetype == "image/jpeg"
        assert msg.media_url == "https://example.com/img.jpg"

    def test_location_message(self):
        msg = InboundMessage(
            id="loc1",
            **{"from": "123@s.whatsapp.net"},
            chat_jid="123@s.whatsapp.net",
            text="",
            timestamp=1234567890,
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco",
        )
        assert msg.latitude == 37.7749
        assert msg.location_name == "San Francisco"

    def test_with_push_name(self):
        msg = InboundMessage(
            id="push1",
            **{"from": "123@s.whatsapp.net"},
            chat_jid="123@s.whatsapp.net",
            push_name="John",
            text="Hi",
            timestamp=1234567890,
        )
        assert msg.push_name == "John"

    def test_all_message_types(self):
        for msg_type in MessageType:
            msg = InboundMessage(
                id=f"test-{msg_type.value}",
                **{"from": "123@s.whatsapp.net"},
                chat_jid="123@s.whatsapp.net",
                text="test",
                type=msg_type,
                timestamp=1234567890,
            )
            assert msg.type == msg_type

    def test_alias_from(self):
        msg = InboundMessage(
            id="alias1",
            **{"from": "123@s.whatsapp.net"},
            chat_jid="123@s.whatsapp.net",
            text="test",
            timestamp=1234567890,
        )
        assert msg.from_jid == "123@s.whatsapp.net"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            InboundMessage(id="test")


class TestMessageType:
    def test_all_values(self):
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

    def test_from_string(self):
        assert MessageType("text") == MessageType.TEXT
        assert MessageType("image") == MessageType.IMAGE
