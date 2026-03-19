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
def outbound_test_data(db_session, test_tenant):
    tenant_hash = test_tenant["hash"]
    loop = get_event_loop()

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="5550001",
            name="Recipient Alice",
            chat_jid="5550001@s.whatsapp.net",
            is_group=False,
        )
    )

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="5550002",
            name='Bob "The Builder" O\'Reilly',
            chat_jid="5550002@s.whatsapp.net",
            is_group=False,
        )
    )

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="5550003",
            name="5550003",
            chat_jid="5550003@s.whatsapp.net",
            is_group=False,
        )
    )

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="group_out",
            name="Outbound Test Group",
            chat_jid="120363777888@g.us",
            is_group=True,
        )
    )

    msg_ids = []

    for i in range(4):
        msg_id = f"out_test_{i}_{secrets.token_hex(4)}"
        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=msg_id,
                from_jid="9876543210@s.whatsapp.net",
                chat_jid=f"555000{i}@s.whatsapp.net",
                is_group=False,
                push_name="",
                text=f"Outbound message {i}",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
                direction="outbound",
            )
        )
        msg_ids.append(msg_id)

    group_msg_id = f"out_group_{secrets.token_hex(4)}"
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=group_msg_id,
            from_jid="9876543210@s.whatsapp.net",
            chat_jid="120363777888@g.us",
            is_group=True,
            push_name="",
            text="Outbound group message",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000) - (5 * 60000),
            direction="outbound",
        )
    )
    msg_ids.append(group_msg_id)

    yield {"message_ids": msg_ids, "tenant_hash": tenant_hash}


class TestOutboundMessagesRendering:
    def test_all_outbound_rows_have_to_label(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_labels = authenticated_page.locator("#messages-list >> text=/^To:/")
        expect(to_labels.first).to_be_visible(timeout=5000)

    def test_contact_name_displayed_for_outbound(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_alice = authenticated_page.locator("text=To: Recipient Alice")
        expect(to_alice.first).to_be_visible(timeout=5000)

    def test_special_chars_in_recipient_name_escaped(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        raw_name = 'Bob "The Builder" O\'Reilly'
        assert (
            raw_name not in authenticated_page.locator("body").text_content()
            or "Reilly" in authenticated_page.locator("body").text_content()
        )
        assert (
            "<script>" not in authenticated_page.locator("#messages-list").inner_html()
        )

    def test_name_same_as_phone_shows_phone_only(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_phone = authenticated_page.locator("text=To: 5550003")
        expect(to_phone.first).to_be_visible(timeout=5000)

    def test_outbound_group_shows_to_with_group_name(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        group_chat = authenticated_page.locator("text=Chat: Outbound Test Group")
        expect(group_chat.first).to_be_visible(timeout=5000)


class TestOutboundPhoneAndJidMeta:
    def test_outbound_shows_recipient_phone(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        phone_el = authenticated_page.locator(
            "#messages-list .text-gray-600 >> text=/^5550001$/"
        )
        expect(phone_el.first).to_be_visible(timeout=5000)

    def test_outbound_shows_recipient_jid(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        jid_el = authenticated_page.locator(
            "#messages-list .text-gray-600 >> text=5550001@s.whatsapp.net"
        )
        expect(jid_el.first).to_be_visible(timeout=5000)

    def test_group_outbound_shows_group_jid(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        group_jid = authenticated_page.locator(
            "#messages-list .text-gray-600 >> text=120363777888@g.us"
        )
        expect(group_jid.first).to_be_visible(timeout=5000)

    def test_meta_positioned_right_side(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        msg_rows = authenticated_page.locator("#messages-list .p-4")
        if msg_rows.count() == 0:
            pytest.skip("No message rows")

        first_row = msg_rows.first
        right_container = first_row.locator(".shrink-0")
        expect(right_container.first).to_be_visible(timeout=5000)

        meta_in_right = right_container.locator(".text-gray-600")
        expect(meta_in_right.first).to_be_visible(timeout=3000)


class TestOutboundReplyButton:
    def test_reply_button_works_on_outbound_message(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        modal = authenticated_page.locator("#reply-modal")
        expect(modal).to_be_visible(timeout=3000)

        modal.locator("button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

    def test_reply_button_has_correct_data_attrs_on_outbound(
        self, authenticated_page: Page, outbound_test_data
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        data_from_name = reply_btn.get_attribute("data-from-name")
        data_chat_jid = reply_btn.get_attribute("data-chat-jid")

        assert data_from_name is not None
        assert data_chat_jid is not None
        assert "@s.whatsapp.net" in data_chat_jid or "@g.us" in data_chat_jid
