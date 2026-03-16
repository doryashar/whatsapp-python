import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, UTC

from src.store.database import Database


TENANT_HASH_1 = "tenant_hash_001"
TENANT_HASH_2 = "tenant_hash_002"


@pytest.fixture
async def db(tmp_path):
    data_dir = tmp_path
    database = Database("", data_dir)
    await database.connect()
    await database.save_tenant(TENANT_HASH_1, "Tenant One", datetime.now(UTC), [])
    await database.save_tenant(TENANT_HASH_2, "Tenant Two", datetime.now(UTC), [])
    yield database
    await database.close()


@pytest.fixture
async def seeded_contacts(db):
    t = datetime.now(UTC)
    await db.upsert_contact(
        tenant_hash=TENANT_HASH_1,
        phone="1111111111",
        name="Alice",
        chat_jid="1111111111@s.whatsapp.net",
        is_group=False,
        message_time=t - timedelta(minutes=30),
    )
    await db.upsert_contact(
        tenant_hash=TENANT_HASH_1,
        phone="2222222222",
        name="Bob",
        chat_jid="2222222222@s.whatsapp.net",
        is_group=False,
        message_time=t - timedelta(minutes=20),
    )
    await db.upsert_contact(
        tenant_hash=TENANT_HASH_1,
        phone="3333333333",
        name="Family Group",
        chat_jid="3333333333@g.us",
        is_group=True,
        message_time=t - timedelta(minutes=10),
    )
    await db.upsert_contact(
        tenant_hash=TENANT_HASH_2,
        phone="4444444444",
        name="Carol",
        chat_jid="4444444444@s.whatsapp.net",
        is_group=False,
        message_time=t - timedelta(minutes=5),
    )
    yield db


class TestGetRecentChatTabs:
    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_list(self, db):
        tabs = await db.get_recent_chat_tabs()
        assert tabs == []

    @pytest.mark.asyncio
    async def test_returns_all_contacts_ordered_by_recency(self, seeded_contacts):
        tabs = await seeded_contacts.get_recent_chat_tabs()
        assert len(tabs) == 4
        chat_jids = [t["chat_jid"] for t in tabs]
        assert chat_jids[0] == "4444444444@s.whatsapp.net"
        assert chat_jids[1] == "3333333333@g.us"
        assert chat_jids[2] == "2222222222@s.whatsapp.net"
        assert chat_jids[3] == "1111111111@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_filters_by_tenant_hash(self, seeded_contacts):
        tabs = await seeded_contacts.get_recent_chat_tabs(tenant_hash=TENANT_HASH_1)
        assert len(tabs) == 3
        for tab in tabs:
            assert tab["chat_jid"] in [
                "1111111111@s.whatsapp.net",
                "2222222222@s.whatsapp.net",
                "3333333333@g.us",
            ]

    @pytest.mark.asyncio
    async def test_respects_limit(self, seeded_contacts):
        tabs = await seeded_contacts.get_recent_chat_tabs(limit=2)
        assert len(tabs) == 2

    @pytest.mark.asyncio
    async def test_is_group_flag_correct(self, seeded_contacts):
        tabs = await seeded_contacts.get_recent_chat_tabs(tenant_hash=TENANT_HASH_1)
        group_tab = [t for t in tabs if t["chat_jid"] == "3333333333@g.us"][0]
        assert group_tab["is_group"] is True
        individual_tab = [
            t for t in tabs if t["chat_jid"] == "1111111111@s.whatsapp.net"
        ][0]
        assert individual_tab["is_group"] is False

    @pytest.mark.asyncio
    async def test_name_none_handled(self, db):
        await db.upsert_contact(
            tenant_hash=TENANT_HASH_1,
            phone="5555555555",
            name=None,
            chat_jid="5555555555@s.whatsapp.net",
            is_group=False,
        )
        tabs = await db.get_recent_chat_tabs()
        assert len(tabs) == 1
        assert tabs[0]["name"] is None


class TestGetContactNamesForChats:
    @pytest.mark.asyncio
    async def test_empty_inputs_return_empty(self, db):
        result = await db.get_contact_names_for_chats([], [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_found_contacts(self, seeded_contacts):
        tenant_hashes = [TENANT_HASH_1]
        chat_jids = ["1111111111@s.whatsapp.net", "3333333333@g.us"]
        result = await seeded_contacts.get_contact_names_for_chats(
            tenant_hashes, chat_jids
        )
        assert len(result) == 2
        assert result[(TENANT_HASH_1, "1111111111@s.whatsapp.net")]["name"] == "Alice"
        assert result[(TENANT_HASH_1, "1111111111@s.whatsapp.net")]["is_group"] is False
        assert result[(TENANT_HASH_1, "3333333333@g.us")]["name"] == "Family Group"
        assert result[(TENANT_HASH_1, "3333333333@g.us")]["is_group"] is True

    @pytest.mark.asyncio
    async def test_partial_match(self, seeded_contacts):
        tenant_hashes = [TENANT_HASH_1, TENANT_HASH_2]
        chat_jids = ["1111111111@s.whatsapp.net", "nonexistent@s.whatsapp.net"]
        result = await seeded_contacts.get_contact_names_for_chats(
            tenant_hashes, chat_jids
        )
        assert len(result) == 1
        assert (TENANT_HASH_1, "1111111111@s.whatsapp.net") in result

    @pytest.mark.asyncio
    async def test_multiple_tenants_same_chat_jid(self, db):
        await db.upsert_contact(
            tenant_hash=TENANT_HASH_1,
            phone="6666666666",
            name="Shared Contact T1",
            chat_jid="6666666666@s.whatsapp.net",
            is_group=False,
        )
        await db.upsert_contact(
            tenant_hash=TENANT_HASH_2,
            phone="6666666666",
            name="Shared Contact T2",
            chat_jid="6666666666@s.whatsapp.net",
            is_group=False,
        )
        result = await db.get_contact_names_for_chats(
            [TENANT_HASH_1, TENANT_HASH_2],
            ["6666666666@s.whatsapp.net"],
        )
        assert len(result) == 2
        assert (
            result[(TENANT_HASH_1, "6666666666@s.whatsapp.net")]["name"]
            == "Shared Contact T1"
        )
        assert (
            result[(TENANT_HASH_2, "6666666666@s.whatsapp.net")]["name"]
            == "Shared Contact T2"
        )

    @pytest.mark.asyncio
    async def test_no_matches_return_empty(self, seeded_contacts):
        result = await seeded_contacts.get_contact_names_for_chats(
            ["nonexistent"],
            ["nonexistent@s.whatsapp.net"],
        )
        assert result == {}


class TestFullFlowIntegration:
    @pytest.mark.asyncio
    async def test_message_creates_contact_and_tab_and_lookup(self, db):
        await db.save_message(
            tenant_hash=TENANT_HASH_1,
            message_id="flow_msg_1",
            from_jid="7777777777@s.whatsapp.net",
            chat_jid="7777777777@s.whatsapp.net",
            is_group=False,
            push_name="Flow User",
            text="Hello from flow",
            timestamp=int(datetime.now(UTC).timestamp()),
            direction="inbound",
        )

        contact = await db.get_contact_by_phone(TENANT_HASH_1, "7777777777")
        assert contact is not None
        assert contact["name"] == "Flow User"
        assert contact["is_group"] is False

        tabs = await db.get_recent_chat_tabs(tenant_hash=TENANT_HASH_1)
        assert len(tabs) >= 1
        tab_chat_jids = [t["chat_jid"] for t in tabs]
        assert "7777777777@s.whatsapp.net" in tab_chat_jids

        names = await db.get_contact_names_for_chats(
            [TENANT_HASH_1],
            ["7777777777@s.whatsapp.net"],
        )
        assert (
            names[(TENANT_HASH_1, "7777777777@s.whatsapp.net")]["name"] == "Flow User"
        )
