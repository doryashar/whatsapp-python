import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestSecurityRendering:
    
    def test_blocked_ips_list_shows_entries(
        self, authenticated_page: Page, blocked_ip: str
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/security")

        expect(authenticated_page.locator("h1")).to_contain_text("Security")

        blocked_ip_text = authenticated_page.locator(f'text="{blocked_ip}"')
        expect(blocked_ip_text).to_be_visible(timeout=5000)

    
    def test_failed_auth_progress_bar(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/security")

        progress = authenticated_page.locator(
            '.progress, [role="progressbar"], .bg-gray-700 > div'
        )
        expect(progress.first).to_be_visible(timeout=5000)

    
    def test_rate_limit_statistics(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/security")

        stats = authenticated_page.locator(':text("blocked"), :text("attempt")')
        expect(stats.first).to_be_visible(timeout=5000)


class TestSecurityActions:
    
    def test_unblock_ip_button(self, authenticated_page: Page, blocked_ip: str):
        authenticated_page.goto(f"{BASE_URL}/admin/security")

        unblock_btn = authenticated_page.locator(
            f'button:near(:text("{blocked_ip}")):has-text("Unblock")'
        )
        if unblock_btn.count() == 0:
            unblock_btn = authenticated_page.locator('button:has-text("Unblock")')

        if unblock_btn.count() > 0:
            unblock_btn.first.click()

    
    def test_clear_failed_attempts(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/security")

        clear_btn = authenticated_page.locator('button:has-text("Clear")')
        if clear_btn.count() > 0:
            clear_btn.first.click()

    
    def test_block_new_ip_via_failed_auth(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/login")

        for _ in range(6):
            authenticated_page.fill('input[name="password"]', "wrongpassword")
            authenticated_page.click('button[type="submit"]')
            authenticated_page.wait_for_timeout(100)

        authenticated_page.goto(f"{BASE_URL}/admin/security")

        blocked = authenticated_page.locator('.bg-red-500, :text("blocked")')
        expect(blocked.first).to_be_visible(timeout=5000)
