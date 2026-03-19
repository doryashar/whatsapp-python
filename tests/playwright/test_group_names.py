import os
import secrets
from datetime import datetime

import pytest
from playwright.sync_api import Page, expect

from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


def get_event_loop():
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@pytest.fixture
def group_messages_with_names(db_session, test_tenant):
    tenant_hash = test_tenant["hash"]
    loop = get_event_loop()

    group_jid_1 = "120363111222@g.us"
    group_name_1 = "Family Reunion 2026"

    group_jid_2 = "120363333444@g.us"
    group_name_2 = "Work Project Team"

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="group_120363111222",
            name=group_name_1,
            chat_jid=group_jid_1,
            is_group=True,
        )
    )

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="group_120363333444",
            name=group_name_2,
            chat_jid=group_jid_2,
            is_group=True,
        )
    )

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="5551001",
            name="Alice",
            chat_jid="5551001@s.whatsapp.net",
            is_group=False,
        )
    )

    for i in range(2):
        msg_id = f"gn_group1_{i}_{secrets.token_hex(4)}"
        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=msg_id,
                from_jid=f"555100{i}@s.whatsapp.net",
                chat_jid=group_jid_1,
                is_group=True,
                push_name=f"Sender {i}",
                text=f"Family chat {i}",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
                direction="inbound",
            )
        )

    for i in range(2):
        msg_id = f"gn_group2_{i}_{secrets.token_hex(4)}"
        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=msg_id,
                from_jid=f"555200{i}@s.whatsapp.net",
                chat_jid=group_jid_2,
                is_group=True,
                push_name=f"Worker {i}",
                text=f"Work chat {i}",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000) - ((i + 2) * 60000),
                direction="inbound",
            )
        )

    msg_id = f"gn_private_{secrets.token_hex(4)}"
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=msg_id,
            from_jid="5551001@s.whatsapp.net",
            chat_jid="5551001@s.whatsapp.net",
            is_group=False,
            push_name="Alice",
            text="Private message",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction="inbound",
        )
    )

    yield {
        "group_jid_1": group_jid_1,
        "group_name_1": group_name_1,
        "group_jid_2": group_jid_2,
        "group_name_2": group_name_2,
    }


class TestGroupTabLabelsShowNames:
    def test_group_tab_shows_group_name_not_numeric_id(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        tabs = authenticated_page.locator(".msg-tab")
        all_tab_text = " ".join([t.text_content() for t in tabs.all()])

        assert "Family Reunion 2026" in all_tab_text, (
            f"Group name 'Family Reunion 2026' not found in tabs. Got: {all_tab_text}"
        )
        assert "Work Project Team" in all_tab_text, (
            f"Group name 'Work Project Team' not found in tabs. Got: {all_tab_text}"
        )

    def test_group_tab_does_not_show_raw_g_us_id(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        tabs = authenticated_page.locator(".msg-tab")
        all_tab_text = " ".join([t.text_content() for t in tabs.all()])

        assert "@g.us" not in all_tab_text, (
            f"Raw group JID found in tabs: {all_tab_text}"
        )

    def test_group_tab_does_not_show_plain_group_label(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        non_all_tabs = authenticated_page.locator(".msg-tab:not(:has-text('All'))")
        if non_all_tabs.count() == 0:
            pytest.skip("No contact tabs found")

        for i in range(non_all_tabs.count()):
            tab_text = non_all_tabs.nth(i).text_content().strip()
            assert tab_text != "group", (
                f"Tab should not show plain 'group' label, got: '{tab_text}'"
            )


class TestGroupMessageShowsGroupName:
    def test_group_message_displays_actual_group_name(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        group_label = authenticated_page.locator("text=Chat: Family Reunion 2026")
        expect(group_label.first).to_be_visible(timeout=5000)

    def test_second_group_also_shows_name(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        group_label = authenticated_page.locator("text=Chat: Work Project Team")
        expect(group_label.first).to_be_visible(timeout=5000)

    def test_group_message_does_not_show_plain_group_label(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        plain_group_label = authenticated_page.locator("text=Chat: group")
        expect(plain_group_label).to_have_count(0, timeout=5000)

    def test_private_message_still_shows_private_label(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        private_label = authenticated_page.locator("text=Chat: private")
        expect(private_label.first).to_be_visible(timeout=5000)

    def test_group_name_styled_orange(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        orange_label = authenticated_page.locator(
            ".text-orange-400:text('Chat: Family Reunion 2026')"
        )
        expect(orange_label.first).to_be_visible(timeout=5000)


class TestGroupTabFiltering:
    def test_clicking_group_tab_filters_to_group_messages(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        group_tab = authenticated_page.locator(
            ".msg-tab:has-text('Family Reunion 2026')"
        )
        if group_tab.count() == 0:
            pytest.skip("Group tab not found")

        group_tab.first.click()
        authenticated_page.wait_for_timeout(2000)

        messages_area = authenticated_page.locator("#messages-list")
        content = messages_area.text_content()

        assert "Family chat" in content, (
            f"Expected 'Family chat' in filtered results. Got: {content[:200]}"
        )
        assert "Work chat" not in content, (
            f"Did not expect 'Work chat' in filtered results. Got: {content[:200]}"
        )

    def test_clicking_all_tab_shows_all_messages(
        self, authenticated_page: Page, group_messages_with_names
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        all_tab = authenticated_page.locator(".msg-tab:has-text('All')")
        if all_tab.count() == 0:
            pytest.skip("All tab not found")

        all_tab.first.click()
        authenticated_page.wait_for_timeout(2000)

        messages_area = authenticated_page.locator("#messages-list")
        content = messages_area.text_content()

        assert "Family chat" in content
        assert "Work chat" in content


@pytest.fixture
def group_without_contact_name(db_session, test_tenant):
    tenant_hash = test_tenant["hash"]
    loop = get_event_loop()

    group_jid = "120363555666@g.us"

    msg_id = f"gn_nocontact_{secrets.token_hex(4)}"
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=msg_id,
            from_jid="5553001@s.whatsapp.net",
            chat_jid=group_jid,
            is_group=True,
            push_name="Someone",
            text="Message in unnamed group",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction="inbound",
            chat_name="Dynamic Group Name",
        )
    )

    yield {
        "group_jid": group_jid,
        "chat_name": "Dynamic Group Name",
    }


class TestGroupMessageWithChatName:
    def test_message_with_chat_name_shows_name_not_group(
        self, authenticated_page: Page, group_without_contact_name
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        plain_group_label = authenticated_page.locator("text=Chat: group")
        expect(plain_group_label).to_have_count(0, timeout=5000)

    def test_message_with_chat_name_creates_contact_entry(
        self, authenticated_page: Page, group_without_contact_name
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(3000)

        tabs = authenticated_page.locator(".msg-tab")
        all_tab_text = " ".join([t.text_content() for t in tabs.all()])

        assert "Dynamic Group Name" in all_tab_text, (
            f"Expected 'Dynamic Group Name' in tabs after chat_name was used. Got: {all_tab_text}"
        )
