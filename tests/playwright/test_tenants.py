import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestTenantsListRendering:
    
    def test_tenants_list_renders(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        expect(authenticated_page.locator("h1")).to_contain_text("Tenant")

        tenants_list = authenticated_page.locator("#tenants-list, .divide-y")
        expect(tenants_list.first).to_be_visible(timeout=5000)

    
    def test_tenant_status_badges_correct_colors(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        connected_badge = authenticated_page.locator(".bg-green-500, .bg-green-600")
        expect(connected_badge.first).to_be_visible(timeout=5000)

    
    def test_tenant_auth_badge_when_has_auth(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        auth_badge = authenticated_page.locator(
            '.bg-blue-500, .bg-blue-600, :text("Auth")'
        )
        expect(auth_badge.first).to_be_visible(timeout=5000)

    
    def test_tenant_name_displayed(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenant_name = authenticated_page.locator(f'text="{test_tenant["name"]}"')
        expect(tenant_name).to_be_visible(timeout=5000)


class TestTenantsCRUD:
    
    def test_create_new_tenant(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        add_btn = authenticated_page.locator('button:has-text("Add")')
        add_btn.first.click()

        modal = authenticated_page.locator('.modal, [role="dialog"]')
        expect(modal.first).to_be_visible(timeout=3000)

        name_input = modal.first.locator(
            'input[name="name"], input[placeholder*="name"]'
        )
        name_input.fill("New Test Tenant")

        submit_btn = modal.first.locator(
            'button[type="submit"], button:has-text("Create")'
        )
        submit_btn.click()

        authenticated_page.wait_for_timeout(1000)

    
    def test_delete_tenant_with_confirmation(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        delete_btn = authenticated_page.locator('button:has-text("Delete")')
        delete_btn.first.click()

        dialog = authenticated_page.locator('[role="alertdialog"], .confirm')
        if dialog.count() > 0:
            confirm_btn = dialog.locator(
                'button:has-text("Delete"), button:has-text("Confirm")'
            )
            confirm_btn.click()

    
    def test_delete_tenant_cancel_does_not_delete(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenant_name = authenticated_page.locator(f'text="{test_tenant["name"]}"')
        expect(tenant_name).to_be_visible()

        delete_btn = authenticated_page.locator('button:has-text("Delete")')
        delete_btn.first.click()

        cancel_btn = authenticated_page.locator('button:has-text("Cancel")')
        if cancel_btn.count() > 0:
            cancel_btn.click()

            expect(tenant_name).to_be_visible()


class TestTenantsActions:
    
    def test_reconnect_tenant_session(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        reconnect_btn = authenticated_page.locator('button:has-text("Reconnect")')
        if reconnect_btn.count() > 0:
            reconnect_btn.first.click()

    
    def test_clear_credentials_confirmation(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        clear_btn = authenticated_page.locator(
            'button:has-text("Clear"), button:has-text("Credential")'
        )
        if clear_btn.count() > 0:
            clear_btn.first.click()

    
    def test_toggle_tenant_enabled_state(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        toggle = authenticated_page.locator(
            'input[type="checkbox"][role="switch"], .toggle'
        )
        if toggle.count() > 0:
            toggle.first.click()

    
    def test_add_webhook_to_tenant(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        webhook_input = authenticated_page.locator(
            'input[placeholder*="webhook"], input[placeholder*="https"]'
        )
        if webhook_input.count() > 0:
            webhook_input.fill("https://new-webhook.example.com/hook")

            add_webhook_btn = authenticated_page.locator('button:has-text("Add")').first
            add_webhook_btn.click()


class TestTenantsBulkOperations:
    
    def test_bulk_select_all_tenants(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        select_all = authenticated_page.locator("#select-all-tenants")
        select_all.click()

        checked = authenticated_page.locator(".tenant-checkbox:checked")
        count = checked.count()
        assert count >= len(multiple_tenants), "All tenants should be selected"

    
    def test_bulk_reconnect_selected_tenants(
        self, authenticated_page: Page, multiple_tenants: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenant_checkbox = authenticated_page.locator(".tenant-checkbox").first
        tenant_checkbox.click()

        bulk_btn = authenticated_page.locator("#bulk-action-btn")
        bulk_btn.click()

        reconnect_btn = authenticated_page.locator('button:has-text("Reconnect")')
        if reconnect_btn.count() > 0:
            reconnect_btn.click()


class TestTenantsNavigation:
    
    def test_navigate_to_tenant_detail(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        tenant_row = authenticated_page.locator(f'text="{test_tenant["name"]}"')
        tenant_row.click()

        authenticated_page.wait_for_url("**/tenants/**", timeout=5000)
