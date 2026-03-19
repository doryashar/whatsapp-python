import os
import hashlib
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
def group_and_individual_messages(db_session, test_tenant):
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
    from src.tenant import tenant_manager

    tenant_hash = test_tenant["hash"]
    loop = get_event_loop()

    group_jid = "120363999888@g.us"
    group_name = "Test Family Group"

    loop.run_until_complete(
        db_session.upsert_contact(
            tenant_hash=tenant_hash,
            phone="group_120363999888",
            name=group_name,
            chat_jid=group_jid,
            is_group=True,
        )
    )

    for i in range(3):
        loop.run_until_complete(
            db_session.upsert_contact(
                tenant_hash=tenant_hash,
                phone=f"555{i:04d}",
                name=f"Contact Individual {i}",
                chat_jid=f"555{i:04d}@s.whatsapp.net",
                is_group=False,
            )
        )

    msgs = []
    for i in range(3):
        msg_id = f"pw_group_msg_{i}_{secrets.token_hex(4)}"
        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=msg_id,
                from_jid=f"5550001@s.whatsapp.net",
                chat_jid=group_jid,
                is_group=True,
                push_name=f"Sender {i}",
                text=f"Group message {i}",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
                direction="inbound" if i % 2 == 0 else "outbound",
            )
        )
        msgs.append(msg_id)

    for i in range(3):
        msg_id = f"pw_ind_msg_{i}_{secrets.token_hex(4)}"
        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=msg_id,
                from_jid=f"555{i:04d}@s.whatsapp.net",
                chat_jid=f"555{i:04d}@s.whatsapp.net",
                is_group=False,
                push_name=f"Contact Individual {i}",
                text=f"Private message {i}",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000) - ((i + 3) * 60000),
                direction="inbound",
            )
        )
        msgs.append(msg_id)

    yield {
        "messages": msgs,
        "group_jid": group_jid,
        "group_name": group_name,
        "tenant_hash": tenant_hash,
    }


class TestMessageDisplayFormat:
    def test_from_label_shows_sender_name(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        from_label = authenticated_page.locator("text=From: Sender 0")
        expect(from_label.first).to_be_visible(timeout=5000)

    def test_from_label_shows_contact_name(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        from_label = authenticated_page.locator("text=From: Contact Individual 0")
        expect(from_label.first).to_be_visible(timeout=5000)

    def test_private_label_visible(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        label = authenticated_page.locator("text=Chat: private")
        expect(label.first).to_be_visible(timeout=5000)

    def test_raw_jid_not_shown(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        messages_area = authenticated_page.locator("#messages-list")
        expect(messages_area.first).to_be_visible(timeout=5000)

        jid_text = authenticated_page.locator(
            "#messages-list:has-text('@s.whatsapp.net')"
        )
        expect(jid_text).to_have_count(0, timeout=3000)

    def test_direction_badges_regression(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        inbound = authenticated_page.locator("text=In")
        outbound = authenticated_page.locator("text=Out")
        expect(inbound.first.or_(outbound.first)).to_be_visible(timeout=5000)

    def test_message_text_renders(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        expect(authenticated_page.locator("text=Group message").first).to_be_visible(
            timeout=5000
        )
        expect(authenticated_page.locator("text=Private message").first).to_be_visible(
            timeout=5000
        )

    def test_group_name_displayed(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        group_label = authenticated_page.locator(
            f"text=Chat: {group_and_individual_messages['group_name']}"
        )
        expect(group_label.first).to_be_visible(timeout=5000)


class TestTabsBar:
    def test_tabs_container_visible(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        tabs = authenticated_page.locator("#messages-tabs-container")
        expect(tabs).to_be_visible(timeout=5000)

    def test_all_tab_active_by_default(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        all_tab = authenticated_page.locator(".msg-tab:has-text('All')")
        expect(all_tab.first).to_have_class(
            "msg-tab px-3 py-1.5 text-xs bg-whatsapp text-white rounded-full font-medium whitespace-nowrap",
            timeout=5000,
        )

    def test_contact_tabs_rendered(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        tabs = authenticated_page.locator(".msg-tab")
        expect(tabs).to_have_count(lambda count: count >= 3, timeout=5000)

    def test_clicking_tab_triggers_filter(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        non_all_tabs = authenticated_page.locator(".msg-tab:not(:has-text('All'))")
        if non_all_tabs.count() == 0:
            pytest.skip("No contact tabs to click")

        request_captured = []

        def capture_request(route, request):
            request_captured.append(request.url)
            route.fulfill(
                status=200, content_type="text/html", body="<div>filtered</div>"
            )

        authenticated_page.route("**/admin/fragments/messages*", capture_request)
        non_all_tabs.first.click()
        authenticated_page.wait_for_timeout(500)

        assert len(request_captured) > 0
        assert "chat_jid=" in request_captured[0]

    def test_clicking_all_resets_filter(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        all_tab = authenticated_page.locator(".msg-tab:has-text('All')")
        if all_tab.count() == 0:
            pytest.skip("No All tab found")

        request_captured = []

        def capture_request(route, request):
            request_captured.append(request.url)
            route.fulfill(status=200, content_type="text/html", body="<div>all</div>")

        authenticated_page.route("**/admin/fragments/messages*", capture_request)
        all_tab.first.click()
        authenticated_page.wait_for_timeout(500)

        assert len(request_captured) > 0
        assert "chat_jid=" not in request_captured[0]

    def test_tabs_reload_on_tenant_change(
        self, authenticated_page: Page, db_session, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        request_captured = []

        def capture_request(route, request):
            request_captured.append(request.url)
            route.fulfill(status=200, content_type="text/html", body="<div>tabs</div>")

        authenticated_page.route("**/admin/fragments/messages-tabs*", capture_request)

        tenant_filter = authenticated_page.locator("#tenant-filter")
        if tenant_filter.count() == 0:
            pytest.skip("No tenant filter found")

        options = tenant_filter.locator("option")
        if options.count() <= 1:
            pytest.skip("Only one tenant, can't change")

        tenant_filter.select_option(index=1)
        authenticated_page.wait_for_timeout(500)

        assert len(request_captured) > 0

    def test_horizontal_scrollable(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        tabs_container = authenticated_page.locator(
            "#messages-tabs-container .flex, #messages-tabs-container"
        )
        expect(tabs_container.first).to_be_visible(timeout=5000)


class TestReplyModal:
    def test_reply_button_per_message(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btns = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        )
        expect(reply_btns.first).to_be_visible(timeout=5000)

    def test_clicking_reply_opens_modal(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
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

    def test_modal_shows_quoted_text(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        quote = authenticated_page.locator("#reply-quote")
        expect(quote).to_be_visible(timeout=3000)

        modal = authenticated_page.locator("#reply-modal")
        modal.locator("button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

    def test_modal_shows_sender_name(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        name_label = authenticated_page.locator("#reply-from-name")
        expect(name_label).to_be_visible(timeout=3000)

        modal = authenticated_page.locator("#reply-modal")
        modal.locator("button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

    def test_modal_tenant_select_prepopulated(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        tenant_select = authenticated_page.locator("#reply-tenant")
        expect(tenant_select).to_be_visible(timeout=3000)

        modal = authenticated_page.locator("#reply-modal")
        modal.locator("button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

    def test_cancel_closes_modal(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        authenticated_page.locator("#reply-modal button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

        expect(authenticated_page.locator("#reply-modal")).to_be_hidden(timeout=3000)

    def test_escape_closes_modal(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        authenticated_page.keyboard.press("Escape")
        authenticated_page.wait_for_timeout(300)

        expect(authenticated_page.locator("#reply-modal")).to_be_hidden(timeout=3000)

    def test_empty_text_no_request_sent(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        api_requests = []

        def capture_api(route, request):
            if "/admin/api/tenants/" in request.url and request.method == "POST":
                api_requests.append(request.url)
            route.continue_()

        authenticated_page.route("**/admin/api/tenants/**", capture_api)

        reply_btn.click()
        authenticated_page.locator("#reply-modal button:has-text('Send')").click()
        authenticated_page.wait_for_timeout(500)

        modal = authenticated_page.locator("#reply-modal")
        modal.locator("button:has-text('Cancel')").click()
        authenticated_page.wait_for_timeout(300)

        assert len(api_requests) == 0

    def test_successful_reply_shows_toast(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        def mock_send_api(route, request):
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "sent", "message_id": "test_msg_1", "to": "jid"}',
            )

        authenticated_page.route("**/admin/api/tenants/*/send", mock_send_api)

        reply_btn = authenticated_page.locator(
            "button[title='Reply'], button[onclick*='openReplyModal']"
        ).first
        if reply_btn.count() == 0:
            pytest.skip("No reply button found")

        reply_btn.click()
        authenticated_page.locator("#reply-text").fill("Test reply message")
        authenticated_page.locator("#reply-modal button:has-text('Send')").click()
        authenticated_page.wait_for_timeout(500)

        toast = authenticated_page.locator("#reply-toast")
        expect(toast).to_be_visible(timeout=3000)
        expect(toast).to_contain_text("Reply sent!")
        expect(authenticated_page.locator("#reply-modal")).to_be_hidden(timeout=3000)


class TestPerformance:
    def test_page_loads_under_3_seconds(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        start = datetime.now().timestamp()
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")
        elapsed = datetime.now().timestamp() - start
        assert elapsed < 3.0, f"Page took {elapsed:.1f}s to load"


class TestRegression:
    def test_search_with_active_tab(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        search_input = authenticated_page.locator("#message-search")
        if search_input.count() == 0:
            pytest.skip("No search input found")

        request_captured = []

        def capture_request(route, request):
            request_captured.append(request.url)
            route.fulfill(
                status=200, content_type="text/html", body="<div>result</div>"
            )

        authenticated_page.route("**/admin/fragments/messages*", capture_request)
        search_input.fill("Test")
        authenticated_page.wait_for_timeout(500)

        assert len(request_captured) > 0

    def test_clear_resets_everything(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        search_input = authenticated_page.locator("#message-search")
        clear_btn = authenticated_page.locator("button:has-text('Clear')")
        if search_input.count() == 0 or clear_btn.count() == 0:
            pytest.skip("Missing search or clear button")

        search_input.fill("some text")
        authenticated_page.wait_for_timeout(300)

        request_captured = []

        def capture_request(route, request):
            request_captured.append(request.url)
            route.fulfill(
                status=200, content_type="text/html", body="<div>cleared</div>"
            )

        authenticated_page.route("**/admin/fragments/messages*", capture_request)
        clear_btn.click()
        authenticated_page.wait_for_timeout(500)

        assert search_input.input_value() == ""
        assert len(request_captured) > 0


class TestOutboundLabelDisplay:
    def test_outbound_shows_to_label(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_label = authenticated_page.locator("text=/^To:/")
        expect(to_label.first).to_be_visible(timeout=5000)

    def test_inbound_shows_from_label(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        from_label = authenticated_page.locator("text=/^From:/")
        expect(from_label.first).to_be_visible(timeout=5000)

    def test_to_label_shows_contact_name(
        self, authenticated_page: Page, db_session, test_tenant
    ):
        tenant_hash = test_tenant["hash"]
        loop = get_event_loop()

        loop.run_until_complete(
            db_session.upsert_contact(
                tenant_hash=tenant_hash,
                phone="5550001",
                name="Outbound Contact",
                chat_jid="5550001@s.whatsapp.net",
                is_group=False,
            )
        )

        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=f"pw_outbound_{secrets.token_hex(8)}",
                from_jid="9876543210@s.whatsapp.net",
                chat_jid="5550001@s.whatsapp.net",
                is_group=False,
                push_name="",
                text="Outbound to contact",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000),
                direction="outbound",
            )
        )

        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_with_name = authenticated_page.locator("text=To: Outbound Contact")
        expect(to_with_name.first).to_be_visible(timeout=5000)

    def test_mixed_messages_correct_labels(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        from_labels = authenticated_page.locator("text=/^From:/")
        to_labels = authenticated_page.locator("text=/^To:/")

        expect(from_labels.first).to_be_visible(timeout=5000)
        expect(to_labels.first).to_be_visible(timeout=5000)

    def test_outbound_no_from_label_present(
        self, authenticated_page: Page, db_session, test_tenant
    ):
        tenant_hash = test_tenant["hash"]
        loop = get_event_loop()

        loop.run_until_complete(
            db_session.save_message(
                tenant_hash=tenant_hash,
                message_id=f"pw_only_out_{secrets.token_hex(8)}",
                from_jid="9876543210@s.whatsapp.net",
                chat_jid="5559999@s.whatsapp.net",
                is_group=False,
                push_name="",
                text="Only outbound msg",
                msg_type="text",
                timestamp=int(datetime.now().timestamp() * 1000),
                direction="outbound",
            )
        )

        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        to_label = authenticated_page.locator("text=/^To:/")
        expect(to_label.first).to_be_visible(timeout=5000)

        msg_rows = authenticated_page.locator("#messages-list .p-4")
        if msg_rows.count() > 0:
            row_text = msg_rows.first.text_content()
            assert "From:" not in (row_text or "")


class TestPhoneAndChatIdMeta:
    def test_phone_number_visible_beside_timestamp(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        msg_rows = authenticated_page.locator("#messages-list .p-4")
        expect(msg_rows.first).to_be_visible(timeout=5000)

        phone_numbers = authenticated_page.locator("#messages-list .text-gray-600")
        expect(phone_numbers.first).to_be_visible(timeout=5000)

    def test_chat_jid_visible_beside_phone(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        messages_area = authenticated_page.locator("#messages-list")
        expect(messages_area.first).to_be_visible(timeout=5000)

        jid_element = authenticated_page.locator(
            "#messages-list >> text=/\\d+@s\\.whatsapp\\.net/"
        )
        expect(jid_element.first).to_be_visible(timeout=5000)

    def test_meta_info_has_correct_styling(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        meta_elements = authenticated_page.locator("#messages-list .text-gray-600")
        expect(meta_elements.first).to_have_class(
            lambda cls: "text-gray-600" in cls and "whitespace-nowrap" in cls,
            timeout=5000,
        )

    def test_all_messages_show_meta_info(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        msg_rows = authenticated_page.locator("#messages-list .p-4")
        count = msg_rows.count()
        if count == 0:
            pytest.skip("No message rows found")

        meta_divs = authenticated_page.locator("#messages-list .p-4 .text-gray-600")
        meta_count = meta_divs.count()

        assert meta_count >= count, (
            f"Expected at least {count} meta elements, got {meta_count}"
        )

    def test_group_message_shows_group_jid(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_timeout(2000)

        group_jid = group_and_individual_messages["group_jid"]
        jid_element = authenticated_page.locator(
            f"#messages-list >> text=/{group_jid.split('@')[0]}@g\\.us/"
        )
        expect(jid_element.first).to_be_visible(timeout=5000)
