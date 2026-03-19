import os
import re
import pytest
from playwright.sync_api import Page, expect

ADMIN_PASSWORD = "test_admin_password_123"
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")


def login(page: Page):
    page.goto(f"{BASE_URL}/admin/login")
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=5000)


# ─── TestLogsPageRendering ───


class TestLogsPageRendering:
    @pytest.mark.playwright
    def test_logs_page_loads(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)
        expect(page.locator("header h1")).to_have_text("Logs & Events")
        expect(page.locator("#log-search")).to_be_visible()
        expect(page.locator("#log-type-filter")).to_be_visible()
        expect(page.locator("#log-level-filter")).to_be_visible()
        expect(page.locator("#log-source-filter")).to_be_visible()
        expect(page.locator("#log-stream")).to_be_visible()
        expect(page.locator("#pause-btn")).to_be_visible()
        expect(page.locator("#scroll-btn")).to_be_visible()
        expect(page.locator("#events-btn")).to_be_visible()

    @pytest.mark.playwright
    def test_logs_page_sidebar_active(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)
        active_link = page.locator('aside a[href="/admin/logs"]')
        expect(active_link).to_have_class("text-whatsapp")

    @pytest.mark.playwright
    def test_logs_page_filter_controls(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        type_options = page.locator("#log-type-filter option").all_inner_texts()
        assert "All Types" in type_options
        assert "Logs" in type_options
        assert "Events" in type_options

        level_options = page.locator("#log-level-filter option").all_inner_texts()
        assert "All Levels" in level_options
        assert "Error" in level_options
        assert "Event" in level_options

        source_options = page.locator("#log-source-filter option").all_inner_texts()
        assert "All Sources" in source_options
        assert "Bridge Events" in source_options
        assert "Webhooks" in source_options

    @pytest.mark.playwright
    def test_logs_page_control_buttons(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        expect(page.locator("#pause-btn")).to_be_visible()
        expect(page.locator("#scroll-btn")).to_be_visible()
        expect(page.locator("#events-btn")).to_be_visible()
        expect(page.get_by_text("Clear")).to_be_visible()

    @pytest.mark.playwright
    def test_logs_page_empty_state(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)
        content = page.locator("#log-stream").inner_text()
        assert "Loading" in content or "No log entries" in content


# ─── TestLogsFiltering ───


class TestLogsFiltering:
    @pytest.mark.playwright
    def test_type_filter_dropdown(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        page.select_option("#log-type-filter", "log")
        page.wait_for_timeout(1000)
        current_value = page.locator("#log-type-filter").input_value()
        assert current_value == "log"

    @pytest.mark.playwright
    def test_level_filter_dropdown(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        page.select_option("#log-level-filter", "ERROR")
        page.wait_for_timeout(1000)
        current_value = page.locator("#log-level-filter").input_value()
        assert current_value == "ERROR"

    @pytest.mark.playwright
    def test_search_input(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        page.fill("#log-search", "test search")
        page.wait_for_timeout(500)
        search_value = page.locator("#log-search").input_value()
        assert search_value == "test search"

    @pytest.mark.playwright
    def test_source_filter_dropdown(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        page.select_option("#log-source-filter", "bridge")
        page.wait_for_timeout(1000)


# ─── TestLogsControls ───


class TestLogsControls:
    @pytest.mark.playwright
    def test_pause_resume_toggle(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        expect(page.locator("#pause-label")).to_have_text("Pause")

        page.click("#pause-btn")
        expect(page.locator("#pause-label")).to_have_text("Resume")

        page.click("#pause-btn")
        expect(page.locator("#pause-label")).to_have_text("Pause")

    @pytest.mark.playwright
    def test_auto_scroll_toggle(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        auto_scroll_active = page.locator("#scroll-btn").get_attribute("class")
        assert "bg-whatsapp" in auto_scroll_active
        expect(page.locator("#scroll-label")).to_have_text("Auto-scroll")

        page.click("#scroll-btn")
        expect(page.locator("#scroll-label")).to_have_text("Scroll off")
        inactive = page.locator("#scroll-btn").get_attribute("class")
        assert "bg-yellow-600/30" in inactive

        page.click("#scroll-btn")
        expect(page.locator("#scroll-label")).to_have_text("Auto-scroll")

    @pytest.mark.playwright
    def test_events_filter_toggle(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        expect(page.locator("#events-label")).to_have_text("Events")

        page.click("#events-btn")
        expect(page.locator("#events-label")).to_have_text("All")
        current_value = page.locator("#log-type-filter").input_value()
        assert current_value == "event"

        page.click("#events-btn")
        expect(page.locator("#events-label")).to_have_text("Events")
        current_value = page.locator("#log-type-filter").input_value()
        assert current_value == ""

    @pytest.mark.playwright
    def test_clear_button_shows_confirm(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        with page.expect_dialog() as dialog_info:
            page.get_by_text("Clear").click()

        dialog = dialog_info.value
        assert "Clear all log entries" in dialog.message

    @pytest.mark.playwright
    def test_clear_cancelled_no_change(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        with page.expect_dialog() as dialog_info:
            page.get_by_text("Clear").click()
        dialog_info.value.dismiss()

        page.wait_for_timeout(500)
        stream = page.locator("#log-stream").inner_text()
        assert "Logs cleared" not in stream


# ─── TestLogsStatusDisplay ───


class TestLogsStatusDisplay:
    @pytest.mark.playwright
    def test_entry_count_display(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-count", timeout=5000)
        expect(page.locator("#log-count")).to_be_visible()

    @pytest.mark.playwright
    def test_status_indicator(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-status", timeout=5000)
        expect(page.locator("#log-status")).to_be_visible()


# ─── TestLogsAccessibility ───


class TestLogsAccessibility:
    @pytest.mark.playwright
    def test_keyboard_navigation(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        page.keyboard.press("Tab")
        focused = page.evaluate("document.activeElement.id")
        assert focused is not None

    @pytest.mark.playwright
    def test_input_labels(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#log-stream", timeout=5000)

        search_input = page.locator("#log-search")
        expect(search_input).to_have_attribute("placeholder", "Search logs...")


# ─── TestEntryDetailModal ───


class TestEntryDetailModal:
    @pytest.mark.playwright
    def test_detail_modal_exists(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#entry-detail-modal", timeout=5000)
        modal = page.locator("#entry-detail-modal")
        expect(modal).to_have_class(re.compile(r"hidden"))

    @pytest.mark.playwright
    def test_detail_modal_closes_on_escape(self, authenticated_page: Page):
        page = authenticated_page
        page.goto(f"{BASE_URL}/admin/logs")
        page.wait_for_selector("#entry-detail-modal", timeout=5000)

        page.evaluate("""
            document.getElementById('entry-detail-modal').classList.remove('hidden');
            document.getElementById('entry-detail-json').textContent = '{"test": true}';
        """)
        expect(page.locator("#entry-detail-modal")).not_to_have_class("hidden")

        page.keyboard.press("Escape")
        expect(page.locator("#entry-detail-modal")).to_have_class("hidden")
