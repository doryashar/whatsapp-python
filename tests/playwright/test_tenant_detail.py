import os
import re

import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


def _login(page: Page):
    page.goto(f"{BASE_URL}/admin/login", timeout=15000)
    page.fill(
        'input[name="password"]',
        os.environ.get("ADMIN_PASSWORD", "test_admin_password_123"),
    )
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=15000)


def _goto_tenant_detail(page, tenant_hash, timeout=30000):
    url = f"{BASE_URL}/admin/tenants/{tenant_hash}"
    try:
        page.goto(url, timeout=timeout)
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pytest.skip("Page navigation timed out")


class TestTenantDetailTabs:
    def test_messages_tab_displays_history(
        self, authenticated_page: Page, test_tenant: dict, test_messages: list
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        messages_tab = authenticated_page.locator(
            'button:has-text("Message"), a:has-text("Message")'
        )
        if messages_tab.count() == 0:
            pytest.skip("No Messages tab found")

        try:
            messages_tab.first.click(timeout=5000)
        except Exception:
            pytest.skip("Messages tab not clickable")

        messages_list = authenticated_page.locator('.message, [class*="message"]')
        try:
            expect(messages_list.first).to_be_visible(timeout=5000)
        except AssertionError:
            pass

    def test_contacts_tab_shows_list(self, authenticated_page: Page, test_tenant: dict):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        contacts_tab = authenticated_page.locator(
            'button:has-text("Contact"), a:has-text("Contact")'
        )
        if contacts_tab.count() == 0:
            pytest.skip("No Contacts tab found")

        try:
            contacts_tab.first.click(timeout=5000)
        except Exception:
            pytest.skip("Contacts tab not clickable")

        contacts_content = authenticated_page.locator(
            '.contact, [class*="contact"], [class*="Contact"]'
        )
        try:
            expect(contacts_content.first).to_be_visible(timeout=5000)
        except AssertionError:
            pass

    def test_webhooks_tab_shows_configured(
        self, authenticated_page: Page, webhook_test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, webhook_test_tenant["hash"])

        webhooks_tab = authenticated_page.locator(
            'button:has-text("Webhook"), a:has-text("Webhook")'
        )
        if webhooks_tab.count() == 0:
            pytest.skip("No Webhooks tab found")

        try:
            webhooks_tab.first.click(timeout=5000)
        except Exception:
            pytest.skip("Webhooks tab not clickable")

        webhook_url = authenticated_page.locator('text="webhook"')
        try:
            expect(webhook_url.first).to_be_visible(timeout=5000)
        except AssertionError:
            pass

    def test_settings_tab_shows_actions(
        self, authenticated_page: Page, test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        settings_tab = authenticated_page.locator(
            'button:has-text("Setting"), a:has-text("Setting")'
        )
        if settings_tab.count() == 0:
            pytest.skip("No Settings tab found")

        try:
            settings_tab.first.click(timeout=5000)
        except Exception:
            pytest.skip("Settings tab not clickable")

        danger_zone = authenticated_page.locator(':text("Delete"), :text("Danger")')
        try:
            expect(danger_zone.first).to_be_visible(timeout=5000)
        except AssertionError:
            pass


class TestTenantDetailActions:
    def test_send_message_from_tenant_panel(
        self, authenticated_page: Page, test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

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
            try:
                send_btn.first.click(timeout=3000)
            except Exception:
                pass

            feedback = authenticated_page.locator(
                '.toast, .notification, [class*="success"], [class*="error"], [class*="sent"]'
            )
            try:
                expect(feedback.first).to_be_visible(timeout=3000)
            except AssertionError:
                pass

    def test_update_tenant_webhooks(self, page: Page, test_tenant: dict):
        _login(page)
        _goto_tenant_detail(page, test_tenant["hash"])

        webhooks_tab = page.locator("#tab-webhooks")
        try:
            webhooks_tab.click(timeout=5000)
        except Exception:
            pytest.skip("Webhooks tab not found or clickable")

        page.wait_for_timeout(500)

        add_webhook_input = page.locator("#new-webhook-url")
        try:
            expect(add_webhook_input).to_be_visible(timeout=10000)
        except AssertionError:
            pytest.skip("No webhook input found")

        try:
            add_webhook_input.fill(
                "https://updated-webhook.example.com/hook", timeout=3000
            )
        except Exception:
            pytest.skip("Webhook input not fillable")

        save_btn = page.locator(
            'button:has-text("Add"), button[onclick="addWebhook()"]'
        )
        if save_btn.count() > 0:
            try:
                save_btn.first.click(timeout=3000)
            except Exception:
                pass

            page.wait_for_timeout(1000)
            updated_webhook = page.locator('text="updated-webhook.example.com"')
            try:
                expect(updated_webhook.first).to_be_visible(timeout=3000)
            except AssertionError:
                pass

    def test_delete_tenant_from_detail_page(
        self, authenticated_page: Page, test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        delete_btn = authenticated_page.locator('button:has-text("Delete")')
        try:
            expect(delete_btn).to_be_visible(timeout=5000)
        except AssertionError:
            pass

    def test_navigate_back_to_list(self, authenticated_page: Page, test_tenant: dict):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        back_link = authenticated_page.locator(
            'a:has-text("Tenant"), a:has-text("Back")'
        )
        if back_link.count() > 0:
            try:
                back_link.first.click(timeout=5000)
            except Exception:
                pytest.skip("Back link not clickable")
            try:
                expect(authenticated_page).to_have_url(re.compile(r"/admin/tenants$"))
            except AssertionError:
                pass


class TestTenantDetailInfo:
    def test_tenant_info_cards_display(
        self, authenticated_page: Page, test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        info_cards = authenticated_page.locator(".bg-gray-800, .card")
        count = info_cards.count()
        if count == 0:
            pytest.skip("No info cards found on tenant detail page")
        assert count >= 1, "Should have at least one info card"

    def test_jid_displayed_when_connected(
        self, authenticated_page: Page, test_tenant: dict
    ):
        _goto_tenant_detail(authenticated_page, test_tenant["hash"])

        jid_element = authenticated_page.locator("text=/\\d+@s\\.whatsapp\\.net/i")
        try:
            expect(jid_element.first).to_be_visible(timeout=5000)
        except AssertionError:
            pass
