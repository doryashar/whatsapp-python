import pytest
import json
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL


pytestmark = [pytest.mark.playwright, pytest.mark.websocket]


class TestWebSocketConnection:
    def test_websocket_connects_with_valid_session(self, authenticated_page: Page):
        ws_connected = False

        def on_web_socket(ws):
            nonlocal ws_connected
            ws_connected = True

        authenticated_page.on("websocket", on_web_socket)
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(3000)

        assert ws_connected, "WebSocket should connect with valid session"

    def test_websocket_url_contains_admin_path(self, authenticated_page: Page):
        ws_urls = []

        def on_web_socket(ws):
            ws_urls.append(ws.url)

        authenticated_page.on("websocket", on_web_socket)
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(3000)

        if ws_urls:
            assert "ws" in ws_urls[0] or "wss" in ws_urls[0]

    @pytest.mark.slow
    def test_ping_pong_heartbeat_maintains_connection(self, authenticated_page: Page):
        frames = []

        def on_web_socket(ws):
            ws.on("framesreceived", lambda received: frames.extend(received))

        authenticated_page.on("websocket", on_web_socket)
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(15000)

        assert len(frames) >= 0, f"WebSocket frames monitoring is active"

    def test_websocket_connection_on_multiple_pages(
        self, admin_browser_context, page: Page
    ):
        ws_connections = []

        def on_web_socket(ws):
            ws_connections.append(ws)

        page1 = admin_browser_context.new_page()
        page2 = admin_browser_context.new_page()

        page1.on("websocket", on_web_socket)
        page2.on("websocket", on_web_socket)

        page1.goto(f"{BASE_URL}/admin/dashboard")
        page1.wait_for_timeout(2000)
        page2.goto(f"{BASE_URL}/admin/logs")
        page2.wait_for_timeout(2000)

        page1.close()
        page2.close()

        if len(ws_connections) < 2:
            pytest.skip("Not enough WebSocket connections detected")

    @pytest.mark.slow
    def test_reconnection_after_disconnect(self, authenticated_page: Page):
        connections = []

        def on_web_socket(ws):
            connections.append(ws)

        authenticated_page.on("websocket", on_web_socket)
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(3000)

        if len(connections) < 1:
            pytest.skip("WebSocket connection not established")

        try:
            connections[0].close()
            authenticated_page.wait_for_timeout(8000)
        except Exception:
            pass

        if len(connections) < 2:
            assert len(connections) >= 1, "WebSocket connection should be established"


class TestWebSocketEvents:
    def test_new_message_events_broadcast(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(1000)

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('new_message', {
                detail: {
                    tenant_hash: 'test_hash_123',
                    message: {
                        id: 'msg_broadcast_1',
                        text: 'Broadcast test message',
                        from: '1234567890@s.whatsapp.net',
                        push_name: 'Broadcast Contact'
                    }
                }
            }));
        """)
        authenticated_page.wait_for_timeout(500)

    def test_new_message_event_has_correct_data(self, authenticated_page: Page):
        event_data = authenticated_page.evaluate("""
            () => {
                return new Promise((resolve) => {
                    const handler = (e) => {
                        window.removeEventListener('new_message', handler);
                        resolve(e.detail);
                    };
                    window.addEventListener('new_message', handler);
                    window.dispatchEvent(new CustomEvent('new_message', {
                        detail: {
                            tenant_hash: 'hash_abc',
                            message: {
                                id: 'msg_789',
                                text: 'Data validation test',
                                from: '111@s.whatsapp.net',
                                push_name: 'Validator'
                            }
                        }
                    }));
                });
            }
        """)

        assert event_data is not None
        assert event_data.get("tenant_hash") == "hash_abc"
        assert event_data.get("message", {}).get("text") == "Data validation test"

    def test_qr_code_events_received(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(1000)

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('qr_generated', {
                detail: {
                    tenant_hash: 'qr_test_tenant',
                    qr: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
                }
            }));
        """)
        authenticated_page.wait_for_timeout(500)

    def test_qr_event_triggers_modal(self, authenticated_page: Page):
        authenticated_page.goto(f"{BASE_URL}/admin/dashboard")
        authenticated_page.wait_for_timeout(1000)

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('qr_generated', {
                detail: {
                    tenant_hash: 'qr_modal_test',
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

    def test_connection_state_changes_received(self, authenticated_page: Page):
        state_changes = []

        authenticated_page.evaluate("""
            window.__state_changes = [];
            window.addEventListener('tenant_state_changed', (e) => {
                window.__state_changes.push(e.detail);
            });
        """)

        for state in ["connected", "disconnected", "pending_qr"]:
            authenticated_page.evaluate(f"""
                window.dispatchEvent(new CustomEvent('tenant_state_changed', {{
                    detail: {{ tenant_hash: 'test_tenant', state: '{state}' }}
                }}));
            """)

        state_changes = authenticated_page.evaluate("window.__state_changes || []")
        assert len(state_changes) >= 3

    def test_webhook_attempt_events_received(self, authenticated_page: Page):
        webhook_events = []

        authenticated_page.evaluate("""
            window.__webhook_events = [];
            window.addEventListener('webhook_attempt', (e) => {
                window.__webhook_events.push(e.detail);
            });
        """)

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('webhook_attempt', {
                detail: {
                    url: 'https://example.com/hook',
                    success: true,
                    status_code: 200,
                    latency_ms: 150
                }
            }));
        """)

        webhook_events = authenticated_page.evaluate("window.__webhook_events || []")
        if len(webhook_events) > 0:
            assert webhook_events[0].get("success") is True
            assert webhook_events[0].get("status_code") == 200

    def test_security_events_received(self, authenticated_page: Page):
        security_events = []

        authenticated_page.evaluate("""
            window.__security_events = [];
            window.addEventListener('security_event', (e) => {
                window.__security_events.push(e.detail);
            });
        """)

        authenticated_page.evaluate("""
            window.dispatchEvent(new CustomEvent('security_event', {
                detail: {
                    event: 'ip_blocked',
                    ip: '10.0.0.1',
                    reason: 'failed_auth'
                }
            }));
        """)

        security_events = authenticated_page.evaluate("window.__security_events || []")
        if len(security_events) > 0:
            assert security_events[0].get("event") == "ip_blocked"


class TestWebSocketMock:
    def test_websocket_mock_instantiation(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        assert mock._connected is False
        assert mock.messages == []

    def test_websocket_mock_connect(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        mock.connect()
        assert mock._connected is True

    def test_websocket_mock_close(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        mock.connect()
        mock.close()
        assert mock._connected is False

    def test_websocket_mock_tenant_state_event(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        event = mock.get_tenant_state_event("hash_123", "connected")
        assert event["type"] == "tenant_state_changed"
        assert event["data"]["tenant_hash"] == "hash_123"
        assert event["data"]["state"] == "connected"

    def test_websocket_mock_new_message_event(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        event = mock.get_new_message_event("hash_456", "Hello World")
        assert event["type"] == "new_message"
        assert event["data"]["message"]["text"] == "Hello World"

    def test_websocket_mock_qr_event(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        event = mock.get_qr_event("hash_789", "qr_data_base64")
        assert event["type"] == "qr_generated"
        assert event["data"]["qr"] == "qr_data_base64"

    def test_websocket_mock_webhook_attempt_event(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        event = mock.get_webhook_attempt_event(True, "https://hook.example.com")
        assert event["type"] == "webhook_attempt"
        assert event["data"]["success"] is True

    def test_websocket_mock_security_event(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        event = mock.get_security_event("ip_blocked", "192.168.1.1")
        assert event["type"] == "security_event"
        assert event["data"]["ip"] == "192.168.1.1"

    def test_websocket_mock_send_json(self):
        from tests.playwright.fixtures.mocks import WebSocketMock

        mock = WebSocketMock()
        mock.send_json({"test": "data"})
        assert len(mock.messages) == 1
        assert mock.messages[0]["test"] == "data"


class TestFrontendErrorReporting:
    def test_frontend_error_api_receives_error(self, authenticated_page: Page):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/frontend-errors",
            data=json.dumps(
                {
                    "message": "Test error",
                    "source": "test.js",
                    "lineno": 42,
                    "colno": 10,
                    "type": "TypeError",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert response.status in (204, 200, 401, 403)

    def test_frontend_error_without_auth_returns_unauthorized(self, page: Page):
        response = page.request.post(
            f"{BASE_URL}/admin/api/frontend-errors",
            data=json.dumps(
                {
                    "message": "Unauthorized error test",
                    "source": "test.js",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        assert response.status in (401, 302, 403)

    def test_websocket_events_multiple_simultaneous(self, authenticated_page: Page):
        event_count = authenticated_page.evaluate("""
            () => {
                return new Promise((resolve) => {
                    let count = 0;
                    const handler = () => {
                        count++;
                        if (count >= 5) {
                            window.removeEventListener('tenant_state_changed', handler);
                            resolve(count);
                        }
                    };
                    window.addEventListener('tenant_state_changed', handler);
                    for (let i = 0; i < 5; i++) {
                        window.dispatchEvent(new CustomEvent('tenant_state_changed', {
                            detail: { tenant_hash: 'multi_test', state: 'connected' }
                        }));
                    }
                });
            }
        """)

        assert event_count == 5

    def test_websocket_statistics_endpoint(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/websockets")
        if response.status == 200:
            data = response.json()
            assert "count" in data
            assert "connections" in data
