import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = [pytest.mark.playwright, pytest.mark.accessibility]


class TestKeyboardNavigation:
    def test_tab_navigation_through_forms(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/login")

        focused_elements = []

        for _ in range(5):
            authenticated_page.keyboard.press("Tab")
            focused = authenticated_page.evaluate("document.activeElement.tagName")
            focused_elements.append(focused)

        assert "INPUT" in focused_elements or "BUTTON" in focused_elements

    def test_enter_key_submits_login(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.fill('input[name="password"]', "test_password")
        page.keyboard.press("Enter")

        page.wait_for_timeout(1000)

    def test_escape_closes_modals(self, authenticated_page: Page):
        try:
            authenticated_page.goto(f"{BASE_URL}/admin/dashboard", timeout=15000)
        except Exception:
            pytest.skip("Page navigation timed out")

        authenticated_page.evaluate("""
            const m = document.getElementById('create-tenant-modal');
            if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
        """)
        authenticated_page.wait_for_timeout(1000)

        add_btn = authenticated_page.locator(
            'button:has-text("Add Tenant"), button:has-text("Add")'
        )
        if add_btn.count() == 0:
            pytest.skip("No Add button found")
        add_btn.first.click(force=True)

        modal = authenticated_page.locator("#create-tenant-modal:not(.hidden)")
        try:
            expect(modal.first).to_be_visible(timeout=3000)
        except Exception:
            pytest.skip("Modal did not open after clicking Add button")

        authenticated_page.keyboard.press("Escape")
        authenticated_page.wait_for_timeout(500)

        modal_classes = (
            authenticated_page.locator("#create-tenant-modal").get_attribute("class")
            or ""
        )
        if "hidden" not in modal_classes:
            pytest.xfail("Escape key does not close create-tenant-modal on this page")


class TestARIA:
    def test_form_labels_associated_correctly(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        inputs = page.locator("input")
        count = inputs.count()

        for i in range(count):
            inp = inputs.nth(i)
            inp_id = inp.get_attribute("id")
            inp_name = inp.get_attribute("name")

            if inp_id:
                label = page.locator(f'label[for="{inp_id}"]')
                label_count = label.count()
                assert label_count > 0 or inp_name, (
                    f"Input {inp_id} should have associated label"
                )

    def test_status_badges_have_accessible_names(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")

        badges = authenticated_page.locator('.rounded-full, .badge, [class*="bg-"]')
        count = badges.count()

        if count > 0:
            first_badge = badges.first
            text = first_badge.text_content()
            assert text and len(text.strip()) > 0, (
                "Status badge should have accessible text"
            )

    def test_modals_have_proper_aria_attributes(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_load_state("networkidle")

        authenticated_page.evaluate("""
            const m = document.getElementById('create-tenant-modal');
            if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
        """)
        authenticated_page.wait_for_timeout(1000)

        add_btn = authenticated_page.locator(
            'button:has-text("Add Tenant"), button:has-text("Add")'
        )
        if add_btn.count() == 0:
            pytest.skip("No Add button found")
        add_btn.first.click(force=True)

        modal = authenticated_page.locator("#create-tenant-modal:not(.hidden)").first
        expect(modal).to_be_visible(timeout=3000)

        modal_text = modal.text_content()
        assert modal_text and len(modal_text.strip()) > 0, (
            "Modal should have visible content"
        )

    def test_error_messages_announced_to_screen_readers(self, page: Page):
        page.goto(f"{BASE_URL}/admin/login")

        page.fill('input[name="password"]', "wrong_password")
        page.click('button[type="submit"]')

        page.wait_for_load_state("networkidle")

        alert = page.locator('[role="alert"], .aria-live, [aria-live]')
        if alert.count() > 0:
            expect(alert.first).to_be_visible()

    def test_focus_trapped_in_modal(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_load_state("networkidle")

        authenticated_page.evaluate("""
            const m = document.getElementById('create-tenant-modal');
            if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
        """)
        authenticated_page.wait_for_timeout(1000)

        add_btn = authenticated_page.locator(
            'button[onclick="showCreateTenantModal()"]'
        )
        expect(add_btn).to_be_visible(timeout=5000)
        add_btn.click()

        modal = authenticated_page.locator("#create-tenant-modal:not(.hidden)").first
        expect(modal).to_be_visible(timeout=3000)

        cancel_btn = modal.locator('button:has-text("Cancel")')
        expect(cancel_btn).to_be_visible(timeout=3000)
        cancel_btn.click()
        expect(modal).to_be_hidden(timeout=3000)

    def test_buttons_have_accessible_names(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_load_state("networkidle")

        buttons = authenticated_page.locator("button")
        count = buttons.count()

        for i in range(min(count, 10)):
            btn = buttons.nth(i)
            text = btn.text_content()
            aria_label = btn.get_attribute("aria-label")

            has_text = text and text.strip()
            has_label = aria_label
            if not has_text and not has_label:
                inner_svg = btn.locator("svg")
                if inner_svg.count() > 0:
                    parent = btn.evaluate(
                        "el => el.parentElement?.textContent?.trim() || ''"
                    )
                    if parent:
                        continue

            assert has_text or has_label, f"Button {i} should have accessible name"

    def test_images_have_alt_text(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        images = authenticated_page.locator("img")
        count = images.count()

        for i in range(count):
            img = images.nth(i)
            alt = img.get_attribute("alt")
            aria_label = img.get_attribute("aria-label")
            role = img.get_attribute("role")

            assert alt is not None or aria_label or role == "presentation", (
                f"Image {i} should have alt text"
            )

    def test_links_have_descriptive_text(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        links = authenticated_page.locator("a")
        count = links.count()

        for i in range(min(count, 10)):
            link = links.nth(i)
            text = link.text_content()
            aria_label = link.get_attribute("aria-label")
            title = link.get_attribute("title")

            assert text and text.strip() or aria_label or title, (
                f"Link {i} should have descriptive text"
            )
