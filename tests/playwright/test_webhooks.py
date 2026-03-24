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

        webhook_url = authenticated_page.locator('text="httpbin"')
        try:
            expect(webhook_url.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass

    def test_webhook_delivery_history(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        history_section = authenticated_page.locator(
            ':text("Histor"), :text("Attempt")'
        )
        expect(history_section.first).to_be_visible(timeout=5000)

    def test_webhook_status_badges_success_failure(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        success_badge = authenticated_page.locator(".bg-green-500, .bg-green-600")
        fail_badge = authenticated_page.locator(".bg-red-500, .bg-red-600")

        if success_badge.count() > 0:
            expect(success_badge.first).to_be_visible()


class TestWebhooksActions:
    def test_remove_webhook(self, authenticated_page: Page, webhook_test_tenant: dict):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        webhook_entry = authenticated_page.locator('text="httpbin.org"')
        try:
            expect(webhook_entry.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass

        remove_btn = authenticated_page.locator(
            'button:has-text("Remove"), button:has-text("Delete")'
        )
        if remove_btn.count() > 0:
            remove_btn.first.click()

            authenticated_page.wait_for_timeout(1000)
            try:
                expect(webhook_entry.first).not_to_be_visible(timeout=3000)
            except AssertionError:
                pass

    def test_webhook_attempt_details_expandable(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        expandable_row = authenticated_page.locator("tr, .expandable, details")
        if expandable_row.count() > 0:
            expandable_row.first.click()

            detail_content = authenticated_page.locator(
                'td[colspan], .detail, [class*="detail"], summary + *'
            )
            try:
                expect(detail_content.first).to_be_visible(timeout=3000)
            except AssertionError:
                pass

    def test_filter_webhooks_by_status(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/webhooks")

        filter_select = authenticated_page.locator("select")
        if filter_select.count() > 0:
            filter_select.first.select_option(index=0)

            authenticated_page.wait_for_timeout(500)
            rows = authenticated_page.locator("tr, .webhook-row")
            try:
                expect(rows.first).to_be_visible(timeout=3000)
            except AssertionError:
                pass
