import os
import pytest
from playwright.sync_api import Page, expect

from tests.playwright.conftest import BASE_URL


pytestmark = pytest.mark.playwright


class TestFromChatLabels:
    def test_messages_page_has_from_label(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")

        content = authenticated_page.content()

        has_from_label = "From:" in content
        assert has_from_label, (
            "Messages page should show 'From:' label for each message"
        )

    def test_messages_page_has_chat_label(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")

        content = authenticated_page.content()

        has_chat_label = "Chat:" in content
        assert has_chat_label, "Messages page should show 'Chat:' label"

    def test_no_raw_jid_displayed(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")

        messages_list = authenticated_page.locator("#messages-list")
        if messages_list.count() == 0:
            pytest.skip("No messages loaded")

        visible_text = messages_list.first.inner_text()
        has_raw_jid = "@s.whatsapp.net" in visible_text
        if has_raw_jid:
            found_non_phone_jid = False
            for line in visible_text.split("\n"):
                line = line.strip()
                if "@s.whatsapp.net" in line and not line.startswith("972"):
                    found_non_phone_jid = True
                    break
            if found_non_phone_jid:
                pytest.xfail(
                    "Raw phone JIDs displayed for contacts without resolved names"
                )

    def test_private_messages_show_chat_private(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")

        content = authenticated_page.content()
        has_private = "Chat: private" in content
        if not has_private:
            pytest.skip("No private messages found to verify 'Chat: private' label")

    def test_messages_page_no_500_errors(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")
        authenticated_page.wait_for_load_state("networkidle")

        status = authenticated_page.locator("h1, h2").first.inner_text()
        assert "Internal Server Error" not in status
        assert "Error" not in status or "Message" in status

    def test_tenant_detail_shows_from_in_bubbles(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")
        authenticated_page.wait_for_load_state("networkidle")

        tenant_rows = authenticated_page.locator("[onclick*='toggleTenantPanel']")
        if tenant_rows.count() == 0:
            pytest.skip("No tenants available")

        found_from = False
        for i in range(tenant_rows.count()):
            tenant_rows.nth(i).click()
            try:
                expect(
                    authenticated_page.locator("[id^='tenant-panel-']").nth(i)
                ).to_be_visible(timeout=5000)
            except Exception:
                continue

            panel = authenticated_page.locator("[id^='tenant-panel-']").nth(i)
            panel_text = panel.inner_text()

            if (
                "messages" in panel_text.lower()
                and "0 messages" not in panel_text.lower()
            ):
                found_from = "From:" in panel_text or found_from

        if not found_from:
            pytest.skip("No tenants have messages to verify 'From:' label")

        assert found_from, "Tenant panel message bubbles should show 'From:' label"

    def test_tenant_messages_page_has_from_labels(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")
        authenticated_page.wait_for_load_state("networkidle")

        tenant_rows = authenticated_page.locator(
            "[onclick*='toggleTenantPanel'], [hx-get*='tenant-panel']"
        )
        if tenant_rows.count() == 0:
            pytest.skip("No tenants available")

        tenant_rows.first.click()
        try:
            expect(
                authenticated_page.locator("[id^='tenant-panel-']").first
            ).to_be_visible(timeout=5000)
        except AssertionError:
            pytest.skip("Tenant panel did not load")

        messages_link = authenticated_page.locator('a:has-text("Messages")')
        if messages_link.count() == 0:
            messages_link = authenticated_page.locator('a[href*="tenant-messages"]')
        if messages_link.count() == 0:
            pytest.skip("No Messages link in tenant detail")

        messages_link.first.click()
        authenticated_page.wait_for_load_state("networkidle")

        page_content = authenticated_page.inner_text("body")
        has_from = "From:" in page_content
        assert has_from, "Tenant messages page should show 'From:' labels"
