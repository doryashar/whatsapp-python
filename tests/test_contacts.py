import pytest
import tempfile
from pathlib import Path
from datetime import datetime, UTC

from src.store.database import Database


@pytest.mark.asyncio
async def test_contacts_table_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        cursor = await db._pool.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'"
        )
        result = await cursor.fetchone()
        assert result is not None

        await db.close()


@pytest.mark.asyncio
async def test_upsert_contact_creates_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.upsert_contact(
            tenant_hash="hash1",
            phone="1234567890",
            name="Dor",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
        )

        contact = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact is not None
        assert contact["phone"] == "1234567890"
        assert contact["name"] == "Dor"
        assert contact["chat_jid"] == "1234567890@s.whatsapp.net"
        assert contact["is_group"] is False
        assert contact["message_count"] == 1

        await db.close()


@pytest.mark.asyncio
async def test_upsert_contact_updates_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.upsert_contact(
            tenant_hash="hash1",
            phone="1234567890",
            name="Dor",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
        )

        await db.upsert_contact(
            tenant_hash="hash1",
            phone="1234567890",
            name="Dor Updated",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
        )

        contact = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact is not None
        assert contact["name"] == "Dor Updated"
        assert contact["message_count"] == 2

        await db.close()


@pytest.mark.asyncio
async def test_upsert_contact_keeps_name_if_new_is_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.upsert_contact(
            tenant_hash="hash1",
            phone="1234567890",
            name="Dor",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
        )

        await db.upsert_contact(
            tenant_hash="hash1",
            phone="1234567890",
            name=None,
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
        )

        contact = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact is not None
        assert contact["name"] == "Dor"

        await db.close()


@pytest.mark.asyncio
async def test_save_message_creates_contact():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="Dor",
            text="Hello",
            timestamp=1234567890,
            direction="inbound",
        )

        contact = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact is not None
        assert contact["phone"] == "1234567890"
        assert contact["name"] == "Dor"

        await db.close()


@pytest.mark.asyncio
async def test_contacts_deduplicated_by_phone():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="Dor",
            text="Hello",
            timestamp=1234567890,
            direction="inbound",
        )

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg2",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="",
            text="World",
            timestamp=1234567891,
            direction="inbound",
        )

        chats = await db.get_recent_chats("hash1")
        assert len(chats) == 1
        assert chats[0]["phone"] == "1234567890"
        assert chats[0]["push_name"] == "Dor"
        assert chats[0]["message_count"] == 2

        await db.close()


@pytest.mark.asyncio
async def test_different_phones_create_separate_contacts():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="Dor",
            text="Hello",
            timestamp=1234567890,
            direction="inbound",
        )

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg2",
            from_jid="972501234567@s.whatsapp.net",
            chat_jid="972501234567@s.whatsapp.net",
            is_group=False,
            push_name="Alice",
            text="World",
            timestamp=1234567891,
            direction="inbound",
        )

        chats = await db.get_recent_chats("hash1")
        assert len(chats) == 2

        await db.close()


@pytest.mark.asyncio
async def test_populate_contacts_from_messages():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        cursor = await db._pool.execute(
            """
            INSERT INTO messages (tenant_hash, message_id, from_jid, chat_jid, is_group, push_name, text, timestamp, direction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hash1",
                "msg1",
                "1234567890@s.whatsapp.net",
                "1234567890@s.whatsapp.net",
                0,
                "Dor",
                "Hello",
                1234567890,
                "inbound",
            ),
        )
        await db._pool.commit()

        count = await db.populate_contacts_from_messages("hash1")
        assert count >= 1

        contact = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact is not None
        assert contact["name"] == "Dor"

        await db.close()


@pytest.mark.asyncio
async def test_groups_vs_individuals():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg1",
            from_jid="120363123456@g.us",
            chat_jid="120363123456@g.us",
            is_group=True,
            push_name="My Group",
            text="Hello group",
            timestamp=1234567890,
            direction="inbound",
        )

        await db.save_message(
            tenant_hash="hash1",
            message_id="msg2",
            from_jid="1234567890@s.whatsapp.net",
            chat_jid="1234567890@s.whatsapp.net",
            is_group=False,
            push_name="Dor",
            text="Hello",
            timestamp=1234567891,
            direction="inbound",
        )

        chats = await db.get_recent_chats("hash1")
        assert len(chats) == 2

        group_chat = [c for c in chats if c["is_group"]][0]
        individual_chat = [c for c in chats if not c["is_group"]][0]

        assert group_chat["is_group"] is True
        assert individual_chat["is_group"] is False

        await db.close()


@pytest.mark.asyncio
async def test_contacts_sync_on_connection():
    """Test that contacts are synced when received from WhatsApp connection"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        # Simulate contacts received from WhatsApp
        contacts = [
            {
                "jid": "1234567890@s.whatsapp.net",
                "name": "John Doe",
                "phone": "1234567890",
                "is_group": False,
            },
            {
                "jid": "972501234567@s.whatsapp.net",
                "name": "Jane Smith",
                "phone": "972501234567",
                "is_group": False,
            },
            {
                "jid": "120363123456@g.us",
                "name": "My Group",
                "phone": None,
                "is_group": True,
            },
        ]

        # Sync contacts as handle_contacts_sync would do
        from src.utils.phone import normalize_phone

        for contact in contacts:
            phone = contact.get("phone")
            jid = contact.get("jid")
            if not phone or not jid:
                continue

            normalized_phone = normalize_phone(phone)
            if not normalized_phone:
                continue

            await db.upsert_contact(
                tenant_hash="hash1",
                phone=normalized_phone,
                name=contact.get("name"),
                chat_jid=jid,
                is_group=contact.get("is_group", False),
            )

        # Verify contacts were saved
        contact1 = await db.get_contact_by_phone("hash1", "1234567890")
        assert contact1 is not None
        assert contact1["name"] == "John Doe"
        assert contact1["is_group"] is False

        contact2 = await db.get_contact_by_phone("hash1", "972501234567")
        assert contact2 is not None
        assert contact2["name"] == "Jane Smith"
        assert contact2["is_group"] is False

        # Group should not be in contacts table since it has no phone
        all_contacts = await db.get_recent_chats("hash1", limit=100)
        assert len(all_contacts) == 2  # Only individual contacts, not groups

        await db.close()
