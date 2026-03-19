import pytest
from unittest.mock import MagicMock, patch

from src.admin.log_buffer import LogBuffer


def _make_tenant(name="TestTenant"):
    tenant = MagicMock()
    tenant.name = name
    return tenant


def _make_buffer():
    return LogBuffer(max_size=100)


@pytest.fixture
def mock_tenant():
    return _make_tenant()


@pytest.fixture
def fresh_log_buffer():
    return _make_buffer()


class TestCaptureMessageEvent:
    @pytest.mark.asyncio
    async def test_message_event_with_text(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "message",
                    mock_tenant,
                    {"from": "12345@s.whatsapp.net", "text": "Hello world"},
                )
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "received" in entries[0]["message"]
            assert "12345" in entries[0]["message"]
            assert "Hello world" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_message_event_no_text(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "message", mock_tenant, {"from": "12345@s.whatsapp.net"}
                )
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert ":" not in entries[0]["message"]
            assert "received" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_message_event_long_text_truncated(
        self, mock_tenant, fresh_log_buffer
    ):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            long_text = "A" * 200
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "message",
                    mock_tenant,
                    {"from": "12345@s.whatsapp.net", "text": long_text},
                )
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert len(entries[0]["message"]) < 200
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_sent_event_with_text(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "sent",
                    mock_tenant,
                    {"to": "98765@s.whatsapp.net", "text": "Outbound"},
                )
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "sent" in entries[0]["message"]
            assert "98765" in entries[0]["message"]
            assert "Outbound" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_message_event_no_jid(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("message", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "received" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig


class TestCaptureConnectionEvents:
    @pytest.mark.asyncio
    async def test_connected_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("connected", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "TestTenant connected" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_disconnected_event_with_reason(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "disconnected", mock_tenant, {"reason": "logout"}
                )
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "TestTenant disconnected" in entries[0]["message"]
            assert "logout" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_reconnecting_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("reconnecting", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "reconnecting" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_reconnect_failed_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("reconnect_failed", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "Reconnect failed" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_connecting_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("connecting", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "connecting" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_disconnected_default_reason(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("disconnected", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "unknown" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig


class TestCaptureOtherEvents:
    @pytest.mark.asyncio
    async def test_qr_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("qr", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "QR code generated" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_auth_update_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("auth.update", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "Auth credentials updated" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_contacts_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("contacts", mock_tenant, {"contacts": []})
            entries, total = await fresh_log_buffer.list()
            assert "Sync contacts" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_chats_history_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("chats_history", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "Sync chats_history" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_message_deleted_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("message_deleted", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "message_deleted" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_message_read_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("message_read", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert "message_read" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig


class TestCaptureEventDetails:
    @pytest.mark.asyncio
    async def test_entry_type_is_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer(
                    "message", mock_tenant, {"from": "123@s.whatsapp.net"}
                )
            entries, total = await fresh_log_buffer.list()
            assert entries[0]["type"] == "event"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_entry_level_is_event(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("connected", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert entries[0]["level"] == "EVENT"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_entry_source_is_bridge(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("message", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert entries[0]["source"] == "bridge"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_entry_details_has_event_type(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("message", mock_tenant, {"from": "123"})
            entries, total = await fresh_log_buffer.list()
            assert entries[0]["details"]["event_type"] == "message"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_entry_tenant_name_populated(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("connected", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert entries[0]["tenant"] == "TestTenant"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_queue_broadcast_called_with_app_event(
        self, mock_tenant, fresh_log_buffer
    ):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast") as mock_bc:
                _capture_event_to_log_buffer("message", mock_tenant, {"from": "123"})
                mock_bc.assert_called_once()
                call_args = mock_bc.call_args
                assert call_args[0][0] == "app_event"
                data = call_args[0][1]
                assert "id" in data
                assert "timestamp" in data
                assert data["type"] == "event"
                assert data["level"] == "EVENT"
                assert data["source"] == "bridge"
                assert "Message" in data["message"]
                assert data["tenant"] == "TestTenant"
        finally:
            main_mod.log_buffer_inst = orig

    @pytest.mark.asyncio
    async def test_unknown_event_type(self, mock_tenant, fresh_log_buffer):
        from src.main import _capture_event_to_log_buffer
        import src.main as main_mod

        orig = main_mod.log_buffer_inst
        main_mod.log_buffer_inst = fresh_log_buffer
        try:
            with patch("src.main.queue_broadcast", new_callable=MagicMock):
                _capture_event_to_log_buffer("unknown_type", mock_tenant, {})
            entries, total = await fresh_log_buffer.list()
            assert total == 1
            assert "unknown_type" in entries[0]["message"]
        finally:
            main_mod.log_buffer_inst = orig
