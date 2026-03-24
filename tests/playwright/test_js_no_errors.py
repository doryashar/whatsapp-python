"""Playwright tests that detect JS ReferenceErrors from missing functions.

These tests enable console error capture and verify that clicking UI elements
does not throw ReferenceError. They do NOT use pytest.skip - they FAIL if JS errors occur.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL, _admin_session


pytestmark = pytest.mark.playwright


def _login(page: Page):
    page.goto(f"{BASE_URL}/admin/login", timeout=15000)
    page.fill(
        'input[name="password"]',
        os.environ.get("ADMIN_PASSWORD", "test_admin_password_123"),
    )
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=15000)


def _create_tenant():
    session = _admin_session()
    import secrets

    name = f"js_test_tenant_{secrets.token_hex(4)}"
    resp = session.post(f"{BASE_URL}/admin/api/tenants", data={"name": name})
    resp.raise_for_status()
    data = resp.json()
    return data["tenant"], session


def _delete_tenant(session, tenant_hash):
    session.delete(f"{BASE_URL}/admin/api/tenants/{tenant_hash}")


class TestDashboardJSNoErrors:
    """Verify dashboard page has no JS ReferenceErrors on interaction."""

    def test_dashboard_page_no_console_errors_on_load(self, authenticated_page: Page):
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        authenticated_page.on("console", _on_console)
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(2000)

        assert not errors, f"ReferenceError(s) on dashboard load: {errors}"

    def test_tenant_actions_modal_opens_without_error(self, page: Page):
        tenant_data, session = _create_tenant()
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        try:
            page.on("console", _on_console)
            _login(page)
            page.goto(f"{BASE_URL}/admin/dashboard")
            page.wait_for_load_state("networkidle")

            page.wait_for_selector('[onclick*="showTenantActions"]', timeout=15000)

            page.locator('[onclick*="showTenantActions"]').first.click()
            page.wait_for_timeout(1000)

            assert not errors, (
                f"ReferenceError(s) when opening tenant actions modal: {errors}"
            )

            modal = page.locator("#tenant-actions-modal:not(.hidden)")
            assert modal.first.is_visible(), (
                "Tenant actions modal did not open - showTenantActions may be broken"
            )
        finally:
            _delete_tenant(session, tenant_data["api_key_hash"])

    def test_close_tenant_actions_modal_without_error(self, page: Page):
        tenant_data, session = _create_tenant()
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        try:
            page.on("console", _on_console)
            _login(page)
            page.goto(f"{BASE_URL}/admin/dashboard")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector('[onclick*="showTenantActions"]', timeout=15000)

            page.evaluate(
                """() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    for (const btn of btns) {
                        if ((btn.getAttribute('onclick') || '').includes('showTenantActions')) {
                            btn.click();
                            return;
                        }
                    }
                }"""
            )
            page.wait_for_timeout(500)

            close_btn = page.locator('#tenant-actions-modal button:has-text("Close")')
            if close_btn.count() > 0:
                close_btn.first.click()
                page.wait_for_timeout(500)

            assert not errors, (
                f"ReferenceError(s) when closing tenant actions modal: {errors}"
            )
        finally:
            _delete_tenant(session, tenant_data["api_key_hash"])

    def test_toggle_tenant_panel_without_error(self, page: Page):
        tenant_data, session = _create_tenant()
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        try:
            page.on("console", _on_console)
            _login(page)
            page.goto(f"{BASE_URL}/admin/dashboard")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector('[onclick*="toggleTenantPanel"]', timeout=15000)

            page.evaluate(
                """() => {
                    const els = Array.from(document.querySelectorAll('[onclick*="toggleTenantPanel"]'));
                    if (els.length > 0) {
                        els[0].click();
                    }
                }"""
            )
            page.wait_for_timeout(1500)

            assert not errors, f"ReferenceError(s) when toggling tenant panel: {errors}"
        finally:
            _delete_tenant(session, tenant_data["api_key_hash"])


class TestTenantsPageJSNoErrors:
    """Verify tenants page has no JS ReferenceErrors on interaction."""

    def test_tenants_page_no_console_errors_on_load(self, authenticated_page: Page):
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        authenticated_page.on("console", _on_console)
        authenticated_page.goto(f"{BASE_URL}/admin/tenants")
        authenticated_page.wait_for_load_state("networkidle")
        authenticated_page.wait_for_timeout(2000)

        assert not errors, f"ReferenceError(s) on tenants page load: {errors}"

    def test_tenants_toggle_enabled_no_error(self, page: Page):
        tenant_data, session = _create_tenant()
        errors = []

        def _on_console(msg):
            if msg.type == "error" and "ReferenceError" in msg.text:
                errors.append(msg.text)

        try:
            page.on("console", _on_console)
            _login(page)
            page.goto(f"{BASE_URL}/admin/tenants")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(
                '[onclick*="toggleEnabled"], [role="switch"]', timeout=15000
            )

            toggle = page.locator(
                'button[onclick*="toggleEnabled"], input[role="switch"]'
            )
            if toggle.count() > 0:
                toggle.first.click()
                page.wait_for_timeout(1000)

            assert not errors, f"ReferenceError(s) when toggling enabled: {errors}"
        finally:
            _delete_tenant(session, tenant_data["api_key_hash"])
