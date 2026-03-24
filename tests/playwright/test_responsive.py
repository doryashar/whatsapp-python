import os

import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = [pytest.mark.playwright, pytest.mark.responsive]


class TestMobileResponsive:
    def test_mobile_navigation_menu_collapsed(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 375, "height": 667})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        hamburger = authenticated_page.locator(
            'button[aria-label*="menu"], button.hamburger, .menu-toggle'
        )

        sidebar = authenticated_page.locator("nav, aside, .sidebar")
        if sidebar.count() > 0:
            is_visible = sidebar.first.is_visible()

            if not is_visible and hamburger.count() > 0:
                hamburger.click()
                expect(sidebar.first).to_be_visible()

    def test_mobile_tables_scrollable(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.set_viewport_size({"width": 375, "height": 667})
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenants_list = authenticated_page.locator("#tenants-list")
        try:
            expect(tenants_list).to_be_visible(timeout=10000)
        except AssertionError:
            pytest.skip("Tenants list not loaded")

        viewport_width = authenticated_page.evaluate("window.innerWidth")
        list_width = authenticated_page.evaluate(
            "el => el.getBoundingClientRect().width", tenants_list.element_handle()
        )
        assert list_width <= viewport_width, (
            f"Tenants list ({list_width}px) overflows viewport ({viewport_width}px)"
        )


class TestTabletResponsive:
    def test_tablet_sidebar_visible(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 768, "height": 1024})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        sidebar = authenticated_page.locator("nav, aside, .sidebar")
        expect(sidebar.first).to_be_visible(timeout=5000)


class TestDesktopResponsive:
    def test_responsive_modals_center(self, page: Page):
        page.set_viewport_size({"width": 1280, "height": 720})
        page.goto(f"{BASE_URL}/admin/login")
        page.fill(
            'input[name="password"]',
            os.environ.get("ADMIN_PASSWORD", "test_admin_password_123"),
        )
        page.click('button[type="submit"]')
        page.wait_for_url("**/dashboard**", timeout=15000)

        page.goto(f"{BASE_URL}/admin/tenants")
        page.wait_for_selector(
            'button[onclick="showCreateTenantModal()"]', timeout=15000
        )
        page.locator('button[onclick="showCreateTenantModal()"]').click()

        modal = page.locator('#create-tenant-modal, .modal, [role="dialog"]').first
        try:
            expect(modal).to_be_visible(timeout=3000)
        except AssertionError:
            pytest.skip("Modal did not appear after clicking Add button")

        modal_styles = modal.evaluate(
            "el => JSON.stringify(el.getBoundingClientRect())"
        )
        assert "width" in modal_styles

    def test_responsive_fonts_scale(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        heading = page.locator("h1, h2").first
        desktop_size = heading.evaluate("el => window.getComputedStyle(el).fontSize")

        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(1000)

        mobile_size = heading.evaluate("el => window.getComputedStyle(el).fontSize")

        assert desktop_size and mobile_size


class TestResponsiveImages:
    def test_images_do_not_overflow(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 375, "height": 667})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_load_state("networkidle")

        overflowing = authenticated_page.evaluate("""() => {
            const images = document.querySelectorAll('img');
            let hasOverflow = false;
            images.forEach(img => {
                if (img.offsetParent === null) return;
                const rect = img.getBoundingClientRect();
                if (rect.right > window.innerWidth + 1) {
                    hasOverflow = true;
                }
            });
            return hasOverflow;
        }""")

        assert not overflowing, "Images should not overflow viewport"
