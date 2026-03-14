import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestDashboardRendering:
    
    def test_dashboard_loads_with_auth(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        expect(authenticated_page.locator("h1")).to_contain_text("Dashboard")
        expect(authenticated_page.locator("header")).to_be_visible()

    
    def test_stats_cards_display(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        stat_cards = authenticated_page.locator('[hx-get*="stats"], .grid > div')
        count = stat_cards.count()
        assert count >= 4, "Should have at least 4 stat cards"

    
    def test_quick_actions_visible(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        add_tenant_btn = authenticated_page.locator(
            'button:has-text("Add"), a:has-text("Add")'
        )
        expect(add_tenant_btn.first).to_be_visible()

    
    def test_recent_tenants_list_renders(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        tenants_list = authenticated_page.locator("#tenants-list, [id*='tenants']")
        expect(tenants_list.first).to_be_visible(timeout=5000)

    
    def test_sidebar_navigation_visible(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        nav_items = ["Dashboard", "Tenants", "Messages", "Security"]
        for item in nav_items:
            nav_link = authenticated_page.locator(
                f'a:has-text("{item}"), nav a:has-text("{item}")'
            )
            expect(nav_link.first).to_be_visible()


class TestDashboardStats:
    
    def test_stats_auto_refresh_via_htmx(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        stats_container = authenticated_page.locator(
            '[hx-trigger*="every"], [hx-get*="stats"]'
        )
        expect(stats_container.first).to_be_visible(timeout=5000)

    
    def test_websocket_panel_visible(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        ws_panel = authenticated_page.locator(
            '[hx-get*="websockets"], :text("WebSocket"), :text("Connections")'
        )
        expect(ws_panel.first).to_be_visible(timeout=5000)


class TestDashboardTenantOperations:
    
    def test_tenant_status_badges(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        status_badge = authenticated_page.locator(
            f".bg-green-500, .bg-yellow-500, .bg-gray-500"
        )
        expect(status_badge.first).to_be_visible(timeout=5000)

    
    def test_create_tenant_modal_opens(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        add_btn = authenticated_page.locator(
            'button:has-text("Add"), button:has-text("Create")'
        )
        add_btn.first.click()

        modal = authenticated_page.locator('.modal, [role="dialog"], .fixed.inset-0')
        expect(modal.first).to_be_visible(timeout=3000)


class TestDashboardBulkOperations:
    
    def test_bulk_selection_checkbox(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        select_all = authenticated_page.locator(
            '#select-all-tenants, input[type="checkbox"]'
        )
        expect(select_all.first).to_be_visible()

        select_all.first.click()

        checkboxes = authenticated_page.locator(".tenant-checkbox:checked")
        count = checkboxes.count()
        assert count >= 1, "At least one checkbox should be checked"

    
    def test_bulk_actions_button_appears(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenant_checkbox = authenticated_page.locator(".tenant-checkbox").first
        tenant_checkbox.click()

        bulk_btn = authenticated_page.locator(
            '#bulk-action-btn, button:has-text("Bulk")'
        )
        expect(bulk_btn.first).to_be_visible(timeout=3000)
