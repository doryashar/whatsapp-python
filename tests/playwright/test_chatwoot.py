import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestChatwootRendering:
    def test_global_config_form_elements(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")
        authenticated_page.wait_for_timeout(3000)
        expect(authenticated_page.locator("h1")).to_contain_text("Chatwoot")

    def test_tenant_chatwoot_list(self, authenticated_page: Page, test_tenant: dict):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")
        authenticated_page.wait_for_timeout(3000)
        content = authenticated_page.locator("#chatwoot-tenants").text_content()
        assert content and len(content.strip()) > 0, (
            "Tenant chatwoot list should have content"
        )


class TestChatwootConfiguration:
    def test_save_global_config(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")
        authenticated_page.wait_for_timeout(3000)
        url_input = authenticated_page.locator('input[name*="url"]')
        if url_input.count() > 0:
            url_input.first.fill("https://chatwoot.example.com")

            save_btn = authenticated_page.locator(
                'button:has-text("Save"), button[type="submit"]'
            )
            if save_btn.count() > 0:
                save_btn.first.click()

    def test_enable_chatwoot_for_tenant(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")

        enable_toggle = authenticated_page.locator(
            'input[type="checkbox"][name*="enabled"]'
        )
        if enable_toggle.count() > 0:
            enable_toggle.first.click()

    def test_configure_sign_messages_option(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")

        config_btn = authenticated_page.locator(
            'button:has-text("Configure"), button:has-text("Settings")'
        )
        if config_btn.count() > 0:
            config_btn.first.click()

            sign_toggle = authenticated_page.locator(
                'input[name*="sign"], label:has-text("Sign")'
            )
            if sign_toggle.count() > 0:
                sign_toggle.first.click()

    def test_configure_reopen_conversation_option(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")

        config_btn = authenticated_page.locator('button:has-text("Configure")')
        if config_btn.count() > 0:
            config_btn.first.click()

            reopen_toggle = authenticated_page.locator(
                'input[name*="reopen"], label:has-text("Reopen")'
            )
            if reopen_toggle.count() > 0:
                reopen_toggle.first.click()


class TestChatwootSyncActions:
    def test_sync_contacts_button(self, authenticated_page: Page, test_tenant: dict):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")

        sync_contacts_btn = authenticated_page.locator(
            'button:has-text("Sync Contact")'
        )
        if sync_contacts_btn.count() > 0:
            sync_contacts_btn.first.click()

    def test_sync_messages_button(self, authenticated_page: Page, test_tenant: dict):
        authenticated_page.goto(f"{BASE_URL}/admin/chatwoot")

        sync_messages_btn = authenticated_page.locator(
            'button:has-text("Sync Message")'
        )
        if sync_messages_btn.count() > 0:
            sync_messages_btn.first.click()
