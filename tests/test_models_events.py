import pytest
from src.models.events import (
    EventType,
    BridgeEvent,
    QREventData,
    ConnectedEventData,
    DisconnectedEventData,
    MessageEventData,
    SentEventData,
)


class TestEventType:
    def test_all_values(self):
        assert EventType.READY == "ready"
        assert EventType.QR == "qr"
        assert EventType.CONNECTED == "connected"
        assert EventType.DISCONNECTED == "disconnected"
        assert EventType.MESSAGE == "message"
        assert EventType.SENT == "sent"
        assert EventType.ERROR == "error"

    def test_value_access(self):
        assert EventType("ready") == EventType.READY
        assert EventType("qr") == EventType.QR

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            EventType("nonexistent")


class TestBridgeEvent:
    def test_default_values(self):
        event = BridgeEvent(method="message", params={"text": "hello"})
        assert event.jsonrpc == "2.0"
        assert event.method == "message"
        assert event.params == {"text": "hello"}

    def test_custom_jsonrpc(self):
        event = BridgeEvent(jsonrpc="1.0", method="test", params={})
        assert event.jsonrpc == "1.0"

    def test_from_dict(self):
        data = {
            "jsonrpc": "2.0",
            "method": "connected",
            "params": {"jid": "test@s.whatsapp.net"},
        }
        event = BridgeEvent(**data)
        assert event.method == "connected"
        assert event.params["jid"] == "test@s.whatsapp.net"


class TestQREventData:
    def test_qr_only(self):
        data = QREventData(qr="base64qrdata")
        assert data.qr == "base64qrdata"
        assert data.qr_data_url is None

    def test_qr_with_data_url(self):
        data = QREventData(qr="base64qrdata", qr_data_url="data:image/png;base64,xxx")
        assert data.qr == "base64qrdata"
        assert data.qr_data_url == "data:image/png;base64,xxx"

    def test_missing_qr_raises(self):
        with pytest.raises(Exception):
            QREventData()


class TestConnectedEventData:
    def test_all_fields(self):
        data = ConnectedEventData(
            jid="123@s.whatsapp.net", phone="1234567890", name="Test"
        )
        assert data.jid == "123@s.whatsapp.net"
        assert data.phone == "1234567890"
        assert data.name == "Test"

    def test_all_none(self):
        data = ConnectedEventData()
        assert data.jid is None
        assert data.phone is None
        assert data.name is None

    def test_partial_fields(self):
        data = ConnectedEventData(jid="123@s.whatsapp.net")
        assert data.jid == "123@s.whatsapp.net"
        assert data.phone is None


class TestDisconnectedEventData:
    def test_defaults(self):
        data = DisconnectedEventData()
        assert data.reason is None
        assert data.should_reconnect is False

    def test_with_reason(self):
        data = DisconnectedEventData(reason=500, should_reconnect=True)
        assert data.reason == 500
        assert data.should_reconnect is True


class TestMessageEventData:
    def test_all_fields(self):
        data = MessageEventData(
            id="msg123",
            from_jid="123@s.whatsapp.net",
            chat_jid="123@s.whatsapp.net",
            is_group=False,
            push_name="User",
            text="Hello",
            type="text",
            timestamp=1234567890,
        )
        assert data.id == "msg123"
        assert data.from_jid == "123@s.whatsapp.net"
        assert data.is_group is False
        assert data.push_name == "User"

    def test_group_message(self):
        data = MessageEventData(
            id="msg456",
            from_jid="456@s.whatsapp.net",
            chat_jid="group@g.us",
            is_group=True,
            text="Hi group",
            type="text",
            timestamp=1234567890,
        )
        assert data.is_group is True

    def test_media_message(self):
        data = MessageEventData(
            id="msg789",
            from_jid="789@s.whatsapp.net",
            chat_jid="789@s.whatsapp.net",
            is_group=False,
            text="",
            type="image",
            timestamp=1234567890,
        )
        assert data.type == "image"

    def test_missing_required_field_raises(self):
        with pytest.raises(Exception):
            MessageEventData()


class TestSentEventData:
    def test_all_fields(self):
        data = SentEventData(message_id="sent123", to="123@s.whatsapp.net")
        assert data.message_id == "sent123"
        assert data.to == "123@s.whatsapp.net"

    def test_missing_required_raises(self):
        with pytest.raises(Exception):
            SentEventData()
