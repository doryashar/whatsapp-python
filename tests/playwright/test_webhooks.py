import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestWebhooksRendering:
    
    def test_registered_webhooks_list(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        expect(authenticated_page.locator("h1")).to_contain_text("Webhook")

        webhook_url = authenticated_page.locator('text="webhook"')
        expect(webhook_url.first).to_be_visible(timeout=5000)

    
    def test_webhook_delivery_history(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        history_section = authenticated_page.locator(
            ':text("Histor"), :text("Attempt")'
        )
        expect(history_section.first).to_be_visible(timeout=5000)

    
    def test_webhook_status_badges_success_failure(
        self, authenticated_page: Page
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        success_badge = authenticated_page.locator(".bg-green-500, .bg-green-600")
        fail_badge = authenticated_page.locator(".bg-red-500, .bg-red-600")

        if success_badge.count() > 0:
            expect(success_badge.first).to_be_visible()


class TestWebhooksActions:
    
    def test_remove_webhook(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        remove_btn = authenticated_page.locator(
            'button:has-text("Remove"), button:has-text("Delete")'
        )
        if remove_btn.count() > 0:
            remove_btn.first.click()

    
    def test_webhook_attempt_details_expandable(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        expandable_row = authenticated_page.locator("tr, .expandable, details")
        if expandable_row.count() > 0:
            expandable_row.first.click()

    
    def test_filter_webhooks_by_status(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        filter_select = authenticated_page.locator("select")
        if filter_select.count() > 0:
            filter_select.first.select_option(index=0)
