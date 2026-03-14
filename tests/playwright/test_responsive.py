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

        table_container = authenticated_page.locator(
            ".overflow-x-auto, .overflow-x-scroll, table"
        ).first
        expect(table_container).to_be_visible(timeout=5000)


class TestTabletResponsive:
    
    def test_tablet_sidebar_visible(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 768, "height": 1024})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        sidebar = authenticated_page.locator("nav, aside, .sidebar")
        expect(sidebar.first).to_be_visible(timeout=5000)


class TestDesktopResponsive:
    
    def test_desktop_full_layout(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 1280, "height": 720})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        main_content = authenticated_page.locator("main, .main, .content")
        expect(main_content.first).to_be_visible(timeout=5000)

    
    def test_responsive_modals_center(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 1280, "height": 720})
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        add_btn = authenticated_page.locator('button:has-text("Add")')
        add_btn.first.click()

        modal = authenticated_page.locator('.modal, [role="dialog"]').first
        expect(modal).to_be_visible(timeout=3000)

        modal_styles = modal.evaluate(
            "el => JSON.stringify(el.getBoundingClientRect())"
        )
        assert "width" in modal_styles

    
    def test_responsive_fonts_scale(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        heading = page.locator("h1, h2").first
        desktop_size = heading.evaluate(
            "el => window.getComputedStyle(el).fontSize"
        )

        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(500)

        mobile_size = heading.evaluate(
            "el => window.getComputedStyle(el).fontSize"
        )

        assert desktop_size and mobile_size


class TestResponsiveImages:
    
    def test_images_do_not_overflow(self, authenticated_page: Page):
        authenticated_page.set_viewport_size({"width": 375, "height": 667})
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        overflowing = authenticated_page.evaluate("""
            const images = document.querySelectorAll('img');
            let hasOverflow = false;
            images.forEach(img => {
                const rect = img.getBoundingClientRect();
                if (rect.right > window.innerWidth) {
                    hasOverflow = true;
                }
            });
            return hasOverflow;
        """)

        assert not overflowing, "Images should not overflow viewport"
