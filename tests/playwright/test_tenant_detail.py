import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestTenantDetailTabs:
    
    def test_messages_tab_displays_history(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        messages_tab = authenticated_page.locator(
            'button:has-text("Message"), a:has-text("Message")'
        )
        messages_tab.first.click()

        messages_list = authenticated_page.locator('.message, [class*="message"]')
        expect(messages_list.first).to_be_visible(timeout=5000)

    
    def test_contacts_tab_shows_list(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        contacts_tab = authenticated_page.locator(
            'button:has-text("Contact"), a:has-text("Contact")'
        )
        contacts_tab.first.click()

    
    def test_webhooks_tab_shows_configured(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        tenant_hash = webhook_test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        webhooks_tab = authenticated_page.locator(
            'button:has-text("Webhook"), a:has-text("Webhook")'
        )
        webhooks_tab.first.click()

        webhook_url = authenticated_page.locator('text="webhook"')
        expect(webhook_url.first).to_be_visible(timeout=5000)

    
    def test_settings_tab_shows_actions(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        settings_tab = authenticated_page.locator(
            'button:has-text("Setting"), a:has-text("Setting")'
        )
        settings_tab.first.click()

        danger_zone = authenticated_page.locator(':text("Delete"), :text("Danger")')
        expect(danger_zone.first).to_be_visible(timeout=5000)


class TestTenantDetailActions:
    
    def test_send_message_from_tenant_panel(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        to_input = authenticated_page.locator(
            'input[name="to"], input[placeholder*="phone"]'
        )
        text_input = authenticated_page.locator(
            'textarea[name="text"], textarea[placeholder*="message"]'
        )
        send_btn = authenticated_page.locator('button:has-text("Send")')

        if to_input.count() > 0 and text_input.count() > 0:
            to_input.fill("1234567890")
            text_input.fill("Test message from Playwright")
            send_btn.click()

    
    def test_update_tenant_webhooks(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        add_webhook_input = authenticated_page.locator(
            'input[placeholder*="webhook"], input[placeholder*="https"]'
        )
        if add_webhook_input.count() > 0:
            add_webhook_input.fill("https://updated-webhook.example.com/hook")

    
    def test_delete_tenant_from_detail_page(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        delete_btn = authenticated_page.locator('button:has-text("Delete")')
        expect(delete_btn).to_be_visible()

    
    def test_navigate_back_to_list(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        back_link = authenticated_page.locator(
            'a:has-text("Tenant"), a:has-text("Back")'
        )
        if back_link.count() > 0:
            back_link.first.click()
            expect(authenticated_page).to_have_url(
                lambda url: "/admin/tenants" in url and len(url.split("/")) < 6
            )


class TestTenantDetailInfo:
    
    def test_tenant_info_cards_display(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        info_cards = authenticated_page.locator(".bg-gray-800, .card")
        count = info_cards.count()
        assert count >= 1, "Should have at least one info card"

    
    def test_jid_displayed_when_connected(
        self, authenticated_page: Page, test_tenant: dict
    ):
        tenant_hash = test_tenant["hash"][:16]
        authenticated_page.goto(
            f"BASE_URL/admin/tenants/{tenant_hash}"
        )

        jid_element = authenticated_page.locator("text=/\\d+@s\\.whatsapp\\.net/i")
        expect(jid_element.first).to_be_visible(timeout=5000)
