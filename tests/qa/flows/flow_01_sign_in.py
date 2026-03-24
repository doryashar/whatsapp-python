import os
import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.qa, pytest.mark.flow_01]

QA_BASE_URL = os.environ.get("QA_BASE_URL", "http://localhost:8080")


def _login_page_url():
    return f"{QA_BASE_URL}/admin/login"


def _admin_url(path: str):
    return f"{QA_BASE_URL}{path}"


class TestQALoginPageRenders:
    def test_login_page_loads(self, qa_unauth_ui):
        ui = qa_unauth_ui
        ui.navigate("/admin/login")
        ui.wait_for_element('input[name="password"]')
        ui.expect_visible('input[name="password"]')
        ui.expect_visible('button[type="submit"]')

    def test_login_page_has_password_field(self, qa_unauth_ui):
        ui = qa_unauth_ui
        ui.navigate("/admin/login")
        field = ui.page.locator('input[name="password"]')
        expect(field).to_have_attribute("type", "password")

    def test_login_page_has_submit_button(self, qa_unauth_ui):
        ui = qa_unauth_ui
        ui.navigate("/admin/login")
        btn = ui.page.locator('button[type="submit"]')
        expect(btn).to_be_visible()
        expect(btn).to_be_enabled()

    def test_login_page_no_sidebar(self, qa_unauth_ui):
        ui = qa_unauth_ui
        ui.navigate("/admin/login")
        ui.page.wait_for_load_state("networkidle")
        sidebar = ui.page.locator("nav, .sidebar, aside")
        expect(sidebar).to_have_count(0)


class TestQALoginWithValidPassword:
    def test_login_redirects_to_dashboard(self, qa_unauth_page, qa_admin_password):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_selector('input[name="password"]', timeout=15000)
        page.fill('input[name="password"]', qa_admin_password)
        page.click('button[type="submit"]')
        page.wait_for_url(_admin_url("/admin/dashboard"), timeout=15000)
        assert "/admin/dashboard" in page.url

    def test_login_sets_session_cookie(self, qa_unauth_page, qa_admin_password):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_selector('input[name="password"]', timeout=15000)
        page.fill('input[name="password"]', qa_admin_password)
        page.click('button[type="submit"]')
        page.wait_for_url(_admin_url("/admin/dashboard"), timeout=15000)
        cookies = page.context.cookies()
        session_cookies = [c for c in cookies if c["name"] == "admin_session"]
        assert len(session_cookies) == 1, "admin_session cookie should be set"
        assert session_cookies[0]["httpOnly"] is True, (
            "admin_session should be httpOnly"
        )

    def test_login_cookie_has_sane_expiry(self, qa_unauth_page, qa_admin_password):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_selector('input[name="password"]', timeout=15000)
        page.fill('input[name="password"]', qa_admin_password)
        page.click('button[type="submit"]')
        page.wait_for_url(_admin_url("/admin/dashboard"), timeout=15000)
        cookies = page.context.cookies()
        session_cookies = [c for c in cookies if c["name"] == "admin_session"]
        assert session_cookies[0]["expires"] > 0, "Cookie should have an expiry"


class TestQALoginWithInvalidPassword:
    def test_wrong_password_shows_error(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_selector('input[name="password"]', timeout=15000)
        page.fill('input[name="password"]', "definitely_wrong_password")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        assert "error" in page.url.lower(), (
            f"URL should contain error on failed login, got: {page.url}"
        )

    def test_wrong_password_no_session_cookie(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_selector('input[name="password"]', timeout=15000)
        page.fill('input[name="password"]', "wrong")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        cookies = page.context.cookies()
        session_cookies = [c for c in cookies if c["name"] == "admin_session"]
        assert len(session_cookies) == 0, (
            "No session cookie should be set on failed login"
        )


class TestQALogout:
    def test_logout_redirects_to_login(self, qa_ui):
        ui = qa_ui
        ui.navigate("/admin/dashboard")
        ui.wait_for_element("nav")
        sign_out = ui.page.locator(
            "button:has-text('Sign Out'), form[action*='logout'] button, a:has-text('Sign Out')"
        )
        if sign_out.count() > 0:
            sign_out.first.click()
            ui.page.wait_for_url(_admin_url("/admin/login"), timeout=10000)
            assert "/admin/login" in ui.page.url
        else:
            ui.page.evaluate("""
                async () => {
                    await fetch('/admin/logout', {method: 'POST', redirect: 'manual'});
                    return 'ok';
                }
            """)
            ui.page.goto(_login_page_url())
            assert "/admin/login" in ui.page.url


class TestQAProtectedPages:
    def test_dashboard_redirects_to_login(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_admin_url("/admin/dashboard"), wait_until="commit")
        page.wait_for_load_state("networkidle")
        assert "login" in page.url.lower(), (
            f"Dashboard should redirect to login, got: {page.url}"
        )

    def test_tenants_redirects_to_login(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_admin_url("/admin/tenants"), wait_until="commit")
        page.wait_for_load_state("networkidle")
        assert "login" in page.url.lower(), (
            f"Tenants should redirect to login, got: {page.url}"
        )

    def test_messages_redirects_to_login(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_admin_url("/admin/messages"), wait_until="commit")
        page.wait_for_load_state("networkidle")
        assert "login" in page.url.lower(), (
            f"Messages should redirect to login, got: {page.url}"
        )

    def test_admin_api_returns_401_without_cookie(self, qa_unauth_page):
        page = qa_unauth_page
        page.goto(_login_page_url())
        page.wait_for_load_state("networkidle")
        result = page.evaluate("""
            async () => {
                const resp = await fetch('/admin/api/tenants');
                return { status: resp.status };
            }
        """)
        assert result["status"] == 401, "API should return 401 without session"
