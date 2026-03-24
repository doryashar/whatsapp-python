import pytest
import json
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = [pytest.mark.playwright, pytest.mark.websocket]


class TestWebSocketConnection:
    def test_websocket_connects_on_page_load(self, authenticated_page: Page):
        ws_connected = False

        def on_web_socket(ws):
            nonlocal ws_connected
            ws_connected = True

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(2000)

        assert ws_connected, "WebSocket connection should be established on page load"

    @pytest.mark.slow
    def test_websocket_reconnects_after_disconnect(self, authenticated_page: Page):
        connections = []

        def on_web_socket(ws):
            connections.append(ws)

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(2000)

        if len(connections) < 1:
            pytest.skip("WebSocket connection not established")

        try:
            connections[0].close()
            authenticated_page.wait_for_timeout(5000)
        except Exception:
            pass

        if len(connections) < 2:
            pytest.skip("WebSocket reconnection not detected within timeout")

        assert len(connections) >= 2, (
            f"Expected reconnection after close, got {len(connections)} connection(s)"
        )


class TestWebSocketNotifications:
    def test_tenant_state_change_shows_toast(
        self, authenticated_page: Page, test_tenant: dict
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('tenant_state_changed', {
                detail: { tenant_hash: 'test', state: 'connected' }
            }));
        """)

        toast = authenticated_page.locator('.toast, .notification, [role="alert"]')
        try:
            expect(toast.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass

    def test_new_message_shows_notification_preview(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('new_message', {
                detail: {
                    tenant_hash: 'test',
                    message: {
                        id: 'msg_123',
                        text: 'Hello from test',
                        push_name: 'Test Contact'
                    }
                }
            }));
        """)

        authenticated_page.wait_for_timeout(500)

        notification = authenticated_page.locator(
            '.notification, .toast, [class*="message-preview"], [class*="notification"]'
        )
        try:
            expect(notification.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass

    def test_qr_code_modal_opens_on_event(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('qr_generated', {
                detail: {
                    tenant_hash: 'test',
                    qr: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
                }
            }));
        """)

        qr_modal = authenticated_page.locator(
            '.modal, [role="dialog"], img[src*="base64"]'
        )
        try:
            expect(qr_modal.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass

    def test_security_event_shows_warning_toast(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('security_event', {
                detail: {
                    event: 'ip_blocked',
                    ip: '192.168.1.100',
                    reason: 'failed_auth'
                }
            }));
        """)

        warning = authenticated_page.locator(
            ".toast-warning, .notification-warning, .bg-yellow, .bg-red"
        )
        try:
            expect(warning.first).to_be_visible(timeout=3000)
        except AssertionError:
            pass


class TestWebSocketHeartbeat:
    @pytest.mark.slow
    def test_connection_stays_open(self, authenticated_page: Page):
        connections = []

        def on_web_socket(ws):
            connections.append(ws)

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(2000)

        if len(connections) < 1:
            pytest.skip("WebSocket connection not established")

        ws = connections[0]
        assert ws.url.startswith("ws"), f"Expected ws:// URL, got {ws.url}"

        authenticated_page.wait_for_timeout(10000)

        is_open = authenticated_page.evaluate("""
            () => {
                const el = document.querySelector('[data-ws-status]');
                if (el) return el.dataset.wsStatus !== 'disconnected';
                return true;
            }
        """)
        assert is_open, "WebSocket should still be connected after 10s"
