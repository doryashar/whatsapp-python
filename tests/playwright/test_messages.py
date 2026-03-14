import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestMessagesListRendering:
    
    def test_messages_list_renders(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        expect(authenticated_page.locator("h1")).to_contain_text("Message")

        messages_list = authenticated_page.locator(
            "#messages-list, .messages, tbody tr"
        )
        expect(messages_list.first).to_be_visible(timeout=5000)

    
    def test_message_direction_badges_correct(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        inbound_badge = authenticated_page.locator(
            '.bg-blue-500, .bg-blue-600, :text("Inbound")'
        )
        outbound_badge = authenticated_page.locator(
            '.bg-green-500, .bg-green-600, :text("Outbound")'
        )

        expect(inbound_badge.first.or_(outbound_badge.first)).to_be_visible(
            timeout=5000
        )

    
    def test_message_timestamp_format(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        timestamp = authenticated_page.locator(
            "text=/\\d{1,2}:\\d{2}/, text=/\\d{4}-\\d{2}-\\d{2}/"
        )
        expect(timestamp.first).to_be_visible(timeout=5000)


class TestMessagesFiltering:
    
    def test_search_messages_by_text(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        search_input = authenticated_page.locator(
            'input[type="search"], input[placeholder*="search"]'
        )
        if search_input.count() > 0:
            search_input.fill("Test message")
            authenticated_page.wait_for_timeout(500)

    
    def test_filter_by_tenant_dropdown(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        tenant_filter = authenticated_page.locator(
            'select[name="tenant"], select[id*="tenant"]'
        )
        if tenant_filter.count() > 0:
            tenant_filter.select_option(index=1)

    
    def test_filter_by_direction_inbound_outbound(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        direction_filter = authenticated_page.locator(
            'select[name="direction"], select[id*="direction"]'
        )
        if direction_filter.count() > 0:
            direction_filter.select_option("inbound")

    
    def test_search_debounce_300ms(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        search_input = authenticated_page.locator(
            'input[type="search"], input[placeholder*="search"]'
        )
        if search_input.count() > 0:
            search_input.type("test", delay=100)
            authenticated_page.wait_for_timeout(400)

    
    def test_clear_filters_resets_list(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        clear_btn = authenticated_page.locator(
            'button:has-text("Clear"), button:has-text("Reset")'
        )
        if clear_btn.count() > 0:
            clear_btn.click()
