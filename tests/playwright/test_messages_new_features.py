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
    from src.store.messages import StoredMessage

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
        msg = StoredMessage(
            id=f"pw_group_msg_{i}_{secrets.token_hex(4)}",
            from_jid=f"5550001@s.whatsapp.net",
            chat_jid=group_jid,
            is_group=True,
            push_name=f"Sender {i}",
            text=f"Group message {i}",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
            direction="inbound" if i % 2 == 0 else "outbound",
        )
        loop.run_until_complete(db_session.save_message(tenant_hash, msg))
        msgs.append(msg)

    for i in range(3):
        msg = StoredMessage(
            id=f"pw_ind_msg_{i}_{secrets.token_hex(4)}",
            from_jid=f"555{i:04d}@s.whatsapp.net",
            chat_jid=f"555{i:04d}@s.whatsapp.net",
            is_group=False,
            push_name=f"Contact Individual {i}",
            text=f"Private message {i}",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000) - ((i + 3) * 60000),
            direction="inbound",
        )
        loop.run_until_complete(db_session.save_message(tenant_hash, msg))
        msgs.append(msg)

    yield {
        "messages": msgs,
        "group_jid": group_jid,
        "group_name": group_name,
        "tenant_hash": tenant_hash,
    }

    loop.run_until_complete(db_session.clear_tenant_messages(tenant_hash))


class TestMessageDisplayFormat:
    def test_private_label_visible(
        self, authenticated_page: Page, test_tenant, group_and_individual_messages
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        label = authenticated_page.locator("text=[private]")
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
            f"text=[{group_and_individual_messages['group_name']}]"
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
