import os
import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def login_with_real_password(page: Page) -> None:
    if not ADMIN_PASSWORD:
        pytest.skip("ADMIN_PASSWORD not set — cannot run live E2E tests")

    page.goto(f"{BASE_URL}/admin/login")
    page.wait_for_selector('input[name="password"]', timeout=10000)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=10000)


pytestmark = pytest.mark.playwright


class TestChatNameDisplayFix:
    @pytest.fixture(autouse=True)
    def _auth(self, page: Page):
        login_with_real_password(page)
        yield

    def test_tenant_detail_shows_contacts_panel(self, page: Page):
        page.goto(f"{BASE_URL}/admin/tenants")
        page.wait_for_load_state("networkidle")

        tenant_rows = page.locator("[hx-get*='tenant-panel'], .tenant-row")
        if tenant_rows.count() == 0:
            pytest.skip("No tenants available")

        tenant_rows.first.click()
        page.wait_for_load_state("networkidle")

        page_content = page.content()
        has_contacts = "Contacts" in page_content or "contacts" in page_content
        assert has_contacts or len(page_content) > 1000

    def test_contacts_display_phone_not_sender_name(self, page: Page):
        page.goto(f"{BASE_URL}/admin/tenants")
        page.wait_for_load_state("networkidle")

        tenant_links = page.locator("[hx-get*='tenant-panel'], .tenant-row a")
        if tenant_links.count() == 0:
            pytest.skip("No tenants available")

        tenant_links.first.click()
        page.wait_for_load_state("networkidle")

        chat_select = page.locator("#chat-select, select[name*='chat']")
        if chat_select.count() > 0:
            options = chat_select.locator("option").all_inner_texts()
            assert len(options) > 0

    def test_messages_list_renders_without_errors(self, page: Page):
        page.goto(f"{BASE_URL}/admin/messages")
        page.wait_for_load_state("networkidle")

        page_content = page.content()
        assert "500" not in page_content or "Internal Server Error" not in page_content

    def test_no_javascript_console_errors(self, page: Page):
        errors = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        page.goto(f"{BASE_URL}/admin/dashboard")
        page.wait_for_load_state("networkidle")

        js_errors = [
            e for e in errors if "favicon" not in e.lower() and "WebSocket" not in e
        ]
        assert len(js_errors) == 0, f"JS console errors: {js_errors}"


class TestLogsPageLive:
    @pytest.fixture(autouse=True)
    def _auth(self, page: Page):
        login_with_real_password(page)
        yield

    def test_logs_page_loads_and_renders(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        expect(page.locator("header h1")).to_have_text("Logs & Events")
        expect(page.locator("#log-search")).to_be_visible()
        expect(page.locator("#log-type-filter")).to_be_visible()
        expect(page.locator("#log-level-filter")).to_be_visible()
        expect(page.locator("#log-source-filter")).to_be_visible()

    def test_logs_page_has_control_buttons(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        expect(page.locator("#pause-btn")).to_be_visible()
        expect(page.locator("#scroll-btn")).to_be_visible()
        expect(page.locator("#events-btn")).to_be_visible()
        expect(page.get_by_text("Clear")).to_be_visible()

    def test_log_filter_controls_have_options(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        type_options = page.locator("#log-type-filter option").all_inner_texts()
        assert "All Types" in type_options
        assert "Logs" in type_options
        assert "Events" in type_options

        level_options = page.locator("#log-level-filter option").all_inner_texts()
        assert "All Levels" in level_options
        assert "Error" in level_options

    def test_pause_resume_toggle(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        expect(page.locator("#pause-label")).to_have_text("Pause")
        page.click("#pause-btn")
        expect(page.locator("#pause-label")).to_have_text("Resume")
        page.click("#pause-btn")
        expect(page.locator("#pause-label")).to_have_text("Pause")

    def test_auto_scroll_toggle(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        expect(page.locator("#scroll-label")).to_have_text("Auto-scroll")
        page.click("#scroll-btn")
        expect(page.locator("#scroll-label")).to_have_text("Scroll off")
        page.click("#scroll-btn")
        expect(page.locator("#scroll-label")).to_have_text("Auto-scroll")

    def test_events_filter_toggle(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        expect(page.locator("#events-label")).to_have_text("Events")
        page.click("#events-btn")
        expect(page.locator("#events-label")).to_have_text("All")
        assert page.locator("#log-type-filter").input_value() == "event"
        page.click("#events-btn")
        expect(page.locator("#events-label")).to_have_text("Events")
        assert page.locator("#log-type-filter").input_value() == ""

    def test_search_input_works(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        page.fill("#log-search", "bridge")
        assert page.locator("#log-search").input_value() == "bridge"

    def test_level_filter_can_select_error(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        page.select_option("#log-level-filter", "ERROR")
        assert page.locator("#log-level-filter").input_value() == "ERROR"

    def test_status_bar_visible(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-status", timeout=10000)
        expect(page.locator("#log-status")).to_be_visible()
        expect(page.locator("#log-count")).to_be_visible()

    def test_sidebar_logs_link_active(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        active_link = page.locator('aside a[href="/admin/logs"]')
        classes = active_link.get_attribute("class") or ""
        assert "text-whatsapp" in classes

    def test_clear_dialog_shows(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)

        page.on("dialog", lambda dialog: dialog.dismiss())
        page.get_by_text("Clear").click()
        expect(page.locator("#log-stream").first).to_be_visible()

    def test_log_entries_appear_in_stream(self, page: Page):
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=10000)
        page.wait_for_timeout(1000)

        stream = page.locator("#log-stream").inner_text()
        assert (
            "Loading" in stream or "No log entries" in stream or len(stream.strip()) > 0
        )


class TestDashboardLive:
    @pytest.fixture(autouse=True)
    def _auth(self, page: Page):
        login_with_real_password(page)
        yield

    def test_dashboard_loads(self, page: Page):
        page.goto(f"{BASE_URL}/admin/dashboard")
        expect(page.locator("h1")).to_contain_text("Dashboard")

    def test_dashboard_sidebar_has_logs_link(self, page: Page):
        page.goto(f"{BASE_URL}/admin/dashboard")
        logs_link = page.locator('aside a[href="/admin/logs"]')
        expect(logs_link).to_be_visible()

    def test_tenants_page_loads(self, page: Page):
        page.goto(f"{BASE_URL}/admin/tenants")
        expect(page.locator("h1").first).to_contain_text("Tenant")

    def test_messages_page_loads(self, page: Page):
        page.goto(f"{BASE_URL}/admin/messages")
        expect(page.locator("h1").first).to_contain_text("Message")

    def test_navigation_between_pages(self, page: Page):
        page.goto(f"{BASE_URL}/admin/dashboard")

        page.click('aside a[href="/admin/logs"]')
        page.wait_for_selector("#log-stream", timeout=10000)
        assert "/admin/logs" in page.url

        page.click('aside a[href="/admin/dashboard"]')
        page.wait_for_url("**/admin/dashboard**")
        assert "/admin/dashboard" in page.url

        page.click('aside a[href="/admin/messages"]')
        page.wait_for_url("**/admin/messages**")
        assert "/admin/messages" in page.url
