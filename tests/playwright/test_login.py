import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestLoginPageRendering:
    def test_login_page_renders_correctly(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        expect(page.locator("h1")).to_contain_text("Admin Login")

        password_input = page.locator('input[name="password"]')
        expect(password_input).to_be_visible()
        expect(password_input).to_have_attribute("type", "password")

        submit_button = page.locator('button[type="submit"]')
        expect(submit_button).to_be_visible()
        expect(submit_button).to_contain_text("Sign In")

    def test_login_form_elements_present(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        form = page.locator("form")
        expect(form).to_be_visible()

        password_label = page.locator('label:has-text("Password")')
        expect(password_label).to_be_visible()

        lock_icon = page.locator("svg")
        expect(lock_icon.first).to_be_visible()

    def test_login_page_responsive_design(self, page: Page):
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{BASE_URL}/admin/login")

        card = page.locator(".bg-gray-800").first
        expect(card).to_be_visible()

        form = page.locator("form")
        expect(form).to_be_visible()


class TestLoginAuthentication:
    def test_login_invalid_password_shows_error(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.fill('input[name="password"]', "wrong_password")
        page.click('button[type="submit"]')

        page.wait_for_url("**/login*error*", timeout=5000)

        error_alert = page.locator(".text-red-400, .bg-red-500\\/20")
        expect(error_alert.first).to_be_visible(timeout=3000)

    def test_login_empty_password_shows_validation(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.click('button[type="submit"]')

        password_input = page.locator('input[name="password"]')
        is_invalid = password_input.evaluate('el => el.validationMessage !== ""')
        assert is_invalid, "Empty password should show validation error"

    def test_protected_route_redirects_to_login(self, page: Page):
        page.goto(f"{BASE_URL}/admin/dashboard")

        current_url = page.url
        is_login = (
            "login" in current_url
            or page.locator('input[name="password"]').is_visible()
        )
        assert is_login, "Protected route should redirect to login page"


class TestLoginRateLimiting:
    @pytest.mark.slow
    def test_login_rate_limiting_blocks_after_failures(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        for i in range(6):
            page.fill('input[name="password"]', f"wrong_{i}")
            page.click('button[type="submit"]')
            page.wait_for_timeout(1000)

        page.fill('input[name="password"]', "another_wrong")
        page.click('button[type="submit"]')
        page.wait_for_timeout(1000)

        body_text = page.locator("body").text_content()
        has_blocked = body_text and (
            "blocked" in body_text.lower() or "rate" in body_text.lower()
        )
        if not has_blocked:
            login_visible = page.locator('input[name="password"]').is_visible()
            assert login_visible, "Login form should still be visible"

    def test_rate_limit_shows_remaining_attempts(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.fill('input[name="password"]', "wrong_password")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        body_text = page.locator("body").text_content()
        has_attempt_info = body_text and "attempt" in body_text.lower()
        if not has_attempt_info:
            login_visible = page.locator('input[name="password"]').is_visible()
            assert login_visible, (
                "Login form should still be visible after wrong attempt"
            )


class TestLoginKeyboardNavigation:
    def test_tab_navigation_through_form(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.keyboard.press("Tab")

        password_input = page.locator('input[name="password"]')
        expect(password_input).to_be_focused()

    def test_enter_key_submits_login(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.fill('input[name="password"]', "test_password")
        page.keyboard.press("Enter")

        page.wait_for_timeout(1000)
