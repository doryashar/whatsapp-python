import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from src.store.database import Database
from src.store.messages import MessageStore, StoredMessage
from src.models.message import InboundMessage, MessageType


class TestEndToEndMediaFlow:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_full_flow_image_message(self, db):
        tenant_hash = "flow_test_image"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        inbound = InboundMessage(
            id="flow_img_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Check this image",
            type=MessageType.IMAGE,
            timestamp=1700000000000,
            media_url="https://mmg.whatsapp.net/img123.jpg",
            mimetype="image/jpeg",
        )

        stored = StoredMessage(
            id=inbound.id,
            from_jid=inbound.from_jid,
            chat_jid=inbound.chat_jid,
            text=inbound.text,
            msg_type=inbound.type.value,
            timestamp=inbound.timestamp,
            direction="inbound",
            media_url=inbound.media_url,
            mimetype=inbound.mimetype,
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=stored.id,
            from_jid=stored.from_jid,
            chat_jid=stored.chat_jid,
            text=stored.text,
            msg_type=stored.type,
            timestamp=stored.timestamp,
            direction=stored.direction,
            media_url=stored.media_url,
            mimetype=stored.mimetype,
        )

        retrieved = await db.get_message_by_id(tenant_hash, "flow_img_1")
        assert retrieved is not None
        assert retrieved["media_url"] == "https://mmg.whatsapp.net/img123.jpg"
        assert retrieved["mimetype"] == "image/jpeg"
        assert retrieved["msg_type"] == "image"
        assert retrieved["text"] == "Check this image"

    @pytest.mark.asyncio
    async def test_full_flow_location_message(self, db):
        tenant_hash = "flow_test_location"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        inbound = InboundMessage(
            id="flow_loc_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            type=MessageType.LOCATION,
            timestamp=1700000000000,
            latitude=48.8566,
            longitude=2.3522,
            location_name="Paris",
            location_address="France",
        )

        stored = StoredMessage(
            id=inbound.id,
            from_jid=inbound.from_jid,
            chat_jid=inbound.chat_jid,
            text=inbound.text,
            msg_type=inbound.type.value,
            timestamp=inbound.timestamp,
            direction="inbound",
            latitude=inbound.latitude,
            longitude=inbound.longitude,
            location_name=inbound.location_name,
            location_address=inbound.location_address,
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=stored.id,
            from_jid=stored.from_jid,
            chat_jid=stored.chat_jid,
            text=stored.text,
            msg_type=stored.type,
            timestamp=stored.timestamp,
            direction=stored.direction,
            latitude=stored.latitude,
            longitude=stored.longitude,
            location_name=stored.location_name,
            location_address=stored.location_address,
        )

        retrieved = await db.get_message_by_id(tenant_hash, "flow_loc_1")
        assert retrieved["latitude"] == 48.8566
        assert retrieved["longitude"] == 2.3522
        assert retrieved["location_name"] == "Paris"

    @pytest.mark.asyncio
    async def test_full_flow_document_message(self, db):
        tenant_hash = "flow_test_doc"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        inbound = InboundMessage(
            id="flow_doc_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Here's the report",
            type=MessageType.DOCUMENT,
            timestamp=1700000000000,
            media_url="https://mmg.whatsapp.net/doc.pdf",
            mimetype="application/pdf",
            filename="Q4_Report.pdf",
        )

        stored = StoredMessage(
            id=inbound.id,
            from_jid=inbound.from_jid,
            chat_jid=inbound.chat_jid,
            text=inbound.text,
            msg_type=inbound.type.value,
            timestamp=inbound.timestamp,
            direction="inbound",
            media_url=inbound.media_url,
            mimetype=inbound.mimetype,
            filename=inbound.filename,
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=stored.id,
            from_jid=stored.from_jid,
            chat_jid=stored.chat_jid,
            text=stored.text,
            msg_type=stored.type,
            timestamp=stored.timestamp,
            direction=stored.direction,
            media_url=stored.media_url,
            mimetype=stored.mimetype,
            filename=stored.filename,
        )

        retrieved = await db.get_message_by_id(tenant_hash, "flow_doc_1")
        assert retrieved["media_url"] == "https://mmg.whatsapp.net/doc.pdf"
        assert retrieved["filename"] == "Q4_Report.pdf"
        assert retrieved["mimetype"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_full_flow_video_message(self, db):
        tenant_hash = "flow_test_video"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        inbound = InboundMessage(
            id="flow_vid_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Funny cat video",
            type=MessageType.VIDEO,
            timestamp=1700000000000,
            media_url="https://mmg.whatsapp.net/cat.mp4",
            mimetype="video/mp4",
        )

        stored = StoredMessage(
            id=inbound.id,
            from_jid=inbound.from_jid,
            chat_jid=inbound.chat_jid,
            text=inbound.text,
            msg_type=inbound.type.value,
            timestamp=inbound.timestamp,
            direction="inbound",
            media_url=inbound.media_url,
            mimetype=inbound.mimetype,
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=stored.id,
            from_jid=stored.from_jid,
            chat_jid=stored.chat_jid,
            text=stored.text,
            msg_type=stored.type,
            timestamp=stored.timestamp,
            direction=stored.direction,
            media_url=stored.media_url,
            mimetype=stored.mimetype,
        )

        retrieved = await db.get_message_by_id(tenant_hash, "flow_vid_1")
        assert retrieved["media_url"] == "https://mmg.whatsapp.net/cat.mp4"
        assert retrieved["msg_type"] == "video"

    @pytest.mark.asyncio
    async def test_full_flow_audio_message(self, db):
        tenant_hash = "flow_test_audio"
        await db.save_tenant(tenant_hash, "test_tenant", datetime.now(UTC), [])

        inbound = InboundMessage(
            id="flow_aud_1",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="",
            type=MessageType.AUDIO,
            timestamp=1700000000000,
            media_url="https://mmg.whatsapp.net/voice.ogg",
            mimetype="audio/ogg",
        )

        stored = StoredMessage(
            id=inbound.id,
            from_jid=inbound.from_jid,
            chat_jid=inbound.chat_jid,
            text=inbound.text,
            msg_type=inbound.type.value,
            timestamp=inbound.timestamp,
            direction="inbound",
            media_url=inbound.media_url,
            mimetype=inbound.mimetype,
        )

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id=stored.id,
            from_jid=stored.from_jid,
            chat_jid=stored.chat_jid,
            text=stored.text,
            msg_type=stored.type,
            timestamp=stored.timestamp,
            direction=stored.direction,
            media_url=stored.media_url,
            mimetype=stored.mimetype,
        )

        retrieved = await db.get_message_by_id(tenant_hash, "flow_aud_1")
        assert retrieved["media_url"] == "https://mmg.whatsapp.net/voice.ogg"
        assert retrieved["msg_type"] == "audio"


class TestMultipleMediaMessages:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_list_messages_with_mixed_types(self, db):
        tenant_hash = "mixed_types_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        messages = [
            {
                "id": "msg_text",
                "msg_type": "text",
                "text": "Hello",
                "media_url": None,
            },
            {
                "id": "msg_img",
                "msg_type": "image",
                "text": "Photo",
                "media_url": "https://example.com/img.jpg",
                "mimetype": "image/jpeg",
            },
            {
                "id": "msg_vid",
                "msg_type": "video",
                "text": "Video",
                "media_url": "https://example.com/vid.mp4",
                "mimetype": "video/mp4",
            },
            {
                "id": "msg_loc",
                "msg_type": "location",
                "text": "",
                "latitude": 51.5,
                "longitude": -0.1,
            },
            {
                "id": "msg_doc",
                "msg_type": "document",
                "text": "Doc",
                "media_url": "https://example.com/doc.pdf",
                "filename": "file.pdf",
            },
        ]

        for i, m in enumerate(messages):
            await db.save_message(
                tenant_hash=tenant_hash,
                message_id=m["id"],
                from_jid="sender@s.whatsapp.net",
                chat_jid="sender@s.whatsapp.net",
                text=m["text"],
                msg_type=m["msg_type"],
                timestamp=1700000000000 + i * 1000,
                direction="inbound",
                media_url=m.get("media_url"),
                mimetype=m.get("mimetype"),
                filename=m.get("filename"),
                latitude=m.get("latitude"),
                longitude=m.get("longitude"),
            )

        listed, total = await db.list_messages(tenant_hash=tenant_hash, limit=10)
        assert total == 5

        text_msg = next(m for m in listed if m["message_id"] == "msg_text")
        assert text_msg["msg_type"] == "text"
        assert text_msg["media_url"] is None

        img_msg = next(m for m in listed if m["message_id"] == "msg_img")
        assert img_msg["media_url"] == "https://example.com/img.jpg"

        loc_msg = next(m for m in listed if m["message_id"] == "msg_loc")
        assert loc_msg["latitude"] == 51.5
        assert loc_msg["longitude"] == -0.1

    @pytest.mark.asyncio
    async def test_message_ordering_preserved(self, db):
        tenant_hash = "ordering_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        for i in range(5):
            await db.save_message(
                tenant_hash=tenant_hash,
                message_id=f"order_msg_{i}",
                from_jid="sender@s.whatsapp.net",
                chat_jid="sender@s.whatsapp.net",
                text=f"Message {i}",
                msg_type="text",
                timestamp=1700000000000 + i * 60000,
                direction="inbound",
            )

        listed, _ = await db.list_messages(tenant_hash=tenant_hash, limit=10)

        assert len(listed) == 5
        message_ids = [m["message_id"] for m in listed]
        assert len(set(message_ids)) == 5


class TestMessageStoreIntegration:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_message_store_add_with_media(self, db):
        tenant_hash = "store_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        store = MessageStore(max_messages=100, tenant_hash=tenant_hash, db=db)

        msg = StoredMessage(
            id="store_img",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Stored image",
            msg_type="image",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/stored.jpg",
            mimetype="image/jpeg",
        )

        await store.add_with_persist(msg)

        retrieved = await db.get_message_by_id(tenant_hash, "store_img")
        assert retrieved is not None
        assert retrieved["media_url"] == "https://example.com/stored.jpg"

    @pytest.mark.asyncio
    async def test_message_store_to_dict_preserves_media(self, db):
        msg = StoredMessage(
            id="dict_test",
            from_jid="sender@s.whatsapp.net",
            chat_jid="sender@s.whatsapp.net",
            text="Test",
            msg_type="video",
            timestamp=1700000000000,
            direction="inbound",
            media_url="https://example.com/dict.mp4",
            mimetype="video/mp4",
            filename="video.mp4",
        )

        d = msg.to_dict()
        assert d["media_url"] == "https://example.com/dict.mp4"
        assert d["mimetype"] == "video/mp4"
        assert d["filename"] == "video.mp4"
        assert d["type"] == "video"


class TestOutboundMediaMessages:
    @pytest.fixture
    async def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            database = Database("", data_dir)
            await database.connect()
            yield database
            await database.close()

    @pytest.mark.asyncio
    async def test_outbound_image_stored_correctly(self, db):
        tenant_hash = "outbound_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="out_img",
            from_jid="me@s.whatsapp.net",
            chat_jid="recipient@s.whatsapp.net",
            text="Sent photo",
            msg_type="image",
            timestamp=1700000000000,
            direction="outbound",
            media_url="https://example.com/sent.jpg",
            mimetype="image/jpeg",
        )

        msg = await db.get_message_by_id(tenant_hash, "out_img")
        assert msg["direction"] == "outbound"
        assert msg["media_url"] == "https://example.com/sent.jpg"
        assert msg["from_jid"] == "me@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_outbound_document_with_filename(self, db):
        tenant_hash = "outbound_doc_test"
        await db.save_tenant(tenant_hash, "test", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash=tenant_hash,
            message_id="out_doc",
            from_jid="me@s.whatsapp.net",
            chat_jid="recipient@s.whatsapp.net",
            text="Here's the file",
            msg_type="document",
            timestamp=1700000000000,
            direction="outbound",
            media_url="https://example.com/sent.pdf",
            mimetype="application/pdf",
            filename="Contract.pdf",
        )

        msg = await db.get_message_by_id(tenant_hash, "out_doc")
        assert msg["direction"] == "outbound"
        assert msg["filename"] == "Contract.pdf"
