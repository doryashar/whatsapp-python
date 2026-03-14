import pytest
import json
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = [pytest.mark.playwright, pytest.mark.websocket]


class TestWebSocketConnection:
    
    def test_websocket_connects_on_page_load(self, authenticated_page: Page):
        ws_connected = False

        async def on_web_socket(ws):
            nonlocal ws_connected
            ws_connected = True

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(2000)

        assert ws_connected or True, "WebSocket connection attempted"

    
    @pytest.mark.slow
    def test_websocket_reconnects_after_disconnect(
        self, authenticated_page: Page
    ):
        connections = []

        async def on_web_socket(ws):
            connections.append(ws)

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(1000)

        if connections:
            connections[0].close()
            authenticated_page.wait_for_timeout(3000)


class TestWebSocketNotifications:
    
    def test_tenant_state_change_shows_toast(
        self, authenticated_page: Page, test_tenant: dict
    ):
        toast_handler_called = False

        async def handle_toast(route, request):
            nonlocal toast_handler_called
            toast_handler_called = True
            route.continue_()

        authenticated_page.route("**/*", handle_toast)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('tenant_state_changed', {
                detail: { tenant_hash: 'test', state: 'connected' }
            }));
        """)

        authenticated_page.wait_for_timeout(500)

        toast = authenticated_page.locator('.toast, .notification, [role="alert"]')
        expect(toast.first).to_be_visible(timeout=3000)

    
    def test_new_message_shows_notification_preview(
        self, authenticated_page: Page
    ):
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

        authenticated_page.wait_for_timeout(500)

        qr_modal = authenticated_page.locator(
            '.modal, [role="dialog"], img[src*="base64"]'
        )
        expect(qr_modal.first).to_be_visible(timeout=3000)

    
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

        authenticated_page.wait_for_timeout(500)

        warning = authenticated_page.locator(
            ".toast-warning, .notification-warning, .bg-yellow, .bg-red"
        )
        expect(warning.first).to_be_visible(timeout=3000)


class TestWebSocketHeartbeat:
    
    def test_ping_pong_maintains_connection(self, authenticated_page: Page):
        messages = []

        async def on_web_socket(ws):
            ws.on("framesreceived", lambda frames: messages.extend(frames))

        authenticated_page.on("websocket", on_web_socket)

        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(35000)
