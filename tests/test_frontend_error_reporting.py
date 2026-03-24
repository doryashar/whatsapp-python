import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from src.admin.log_buffer import LogEntry
from tests.conftest import ADMIN_PASSWORD


class TestFrontendErrorEndpoint:
    @pytest.mark.asyncio
    async def test_post_frontend_error_writes_to_log_buffer(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {
            "message": "Uncaught TypeError: foo is not defined",
            "source": "http://localhost:8080/admin/dashboard",
            "lineno": 42,
            "colno": 15,
            "stack": "Error: foo is not defined\n    at bar (dashboard:42:15)",
            "type": "Error",
            "url": "http://localhost:8080/admin/dashboard",
            "user_agent": "Mozilla/5.0",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.post("/admin/api/frontend-errors", json=payload)

        assert response.status_code == 204

        entries, total = await buf.list(source_filter="frontend.http")
        assert total >= 1
        err = entries[0]
        assert err["level"] == "ERROR"
        assert err["source"] == "frontend.http"
        assert "foo is not defined" in err["message"]
        assert "42" in err["message"]
        assert err["details"]["lineno"] == 42
        assert err["details"]["colno"] == 15
        assert err["details"]["error_type"] == "Error"
        assert err["details"]["user_agent"] == "Mozilla/5.0"

    @pytest.mark.asyncio
    async def test_post_frontend_error_minimal_payload(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.post(
                "/admin/api/frontend-errors",
                json={"message": "Something broke"},
            )

        assert response.status_code == 204

        entries, total = await buf.list(source_filter="frontend.http")
        assert total >= 1
        assert "Something broke" in entries[0]["message"]

    @pytest.mark.asyncio
    async def test_post_frontend_error_message_format_with_source_and_line(
        self, setup_tenant_manager
    ):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {
            "message": "test error",
            "source": "app.js",
            "lineno": 10,
            "colno": 5,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await client.post("/admin/api/frontend-errors", json=payload)

        entries, _ = await buf.list(source_filter="frontend.http")
        assert entries[0]["message"] == "test error (app.js:10:5)"

    @pytest.mark.asyncio
    async def test_post_frontend_error_without_source_no_parens(
        self, setup_tenant_manager
    ):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {
            "message": "Unhandled rejection",
            "type": "UnhandledRejection",
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await client.post("/admin/api/frontend-errors", json=payload)

        entries, _ = await buf.list(source_filter="frontend.http")
        assert entries[0]["message"] == "Unhandled rejection"
        assert entries[0]["details"]["error_type"] == "UnhandledRejection"

    @pytest.mark.asyncio
    async def test_post_frontend_error_appears_in_log_fragment(
        self, setup_tenant_manager
    ):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {
            "message": "fragment test error",
            "source": "test.js",
            "lineno": 1,
        }

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await client.post("/admin/api/frontend-errors", json=payload)
            response = await client.get("/admin/fragments/logs?source=frontend")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any("fragment test error" in e["message"] for e in data["entries"])

    @pytest.mark.asyncio
    async def test_post_frontend_error_broadcast_via_websocket(
        self, setup_tenant_manager
    ):
        from src.admin import log_buffer as log_buf_mod
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {
            "message": "ws broadcast test",
            "source": "ws-test.js",
            "lineno": 99,
        }

        captured = []

        def capture(event_type, data):
            captured.append((event_type, data))

        with patch.object(log_buf_mod, "queue_broadcast", side_effect=capture):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=True,
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                await client.post("/admin/api/frontend-errors", json=payload)

        assert any(c[0] == "app_event" for c in captured)
        event_data = next(c[1] for c in captured if c[0] == "app_event")
        assert event_data["source"] == "frontend.http"
        assert "ws broadcast test" in event_data["message"]

    @pytest.mark.asyncio
    async def test_post_frontend_error_rejected_without_auth(
        self, setup_tenant_manager
    ):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst
        await buf.clear()

        payload = {"message": "should not be logged"}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/api/frontend-errors",
                json=payload,
                headers={"accept": "text/html"},
            )

        assert response.status_code == 302
        assert "/admin/login" in response.headers["location"]

        entries, total = await buf.list(source_filter="frontend.http")
        assert total == 0


class TestFrontendErrorWebSocketHandler:
    @pytest.mark.asyncio
    async def test_ws_frontend_error_captured_in_log_buffer(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import _capture_frontend_error_to_log_buffer

        buf = main_mod.log_buffer_inst
        await buf.clear()

        msg = {
            "type": "frontend_error",
            "data": {
                "message": "WS error test",
                "source": "page.js",
                "lineno": 7,
                "colno": 3,
                "stack": "at line 7",
                "url": "http://localhost/admin/dashboard",
                "user_agent": "TestAgent",
            },
        }

        _capture_frontend_error_to_log_buffer(msg)

        entries, total = await buf.list(source_filter="frontend.ws")
        assert total >= 1
        assert entries[0]["level"] == "ERROR"
        assert "WS error test" in entries[0]["message"]
        assert entries[0]["details"]["source"] == "page.js"
        assert entries[0]["details"]["lineno"] == 7

    @pytest.mark.asyncio
    async def test_ws_frontend_error_missing_data(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import _capture_frontend_error_to_log_buffer

        buf = main_mod.log_buffer_inst
        await buf.clear()

        _capture_frontend_error_to_log_buffer({"type": "frontend_error"})

        entries, total = await buf.list(source_filter="frontend.ws")
        assert total >= 1
        assert entries[0]["message"] == "Unknown frontend error"

    @pytest.mark.asyncio
    async def test_ws_frontend_error_with_rejection(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import _capture_frontend_error_to_log_buffer

        buf = main_mod.log_buffer_inst
        await buf.clear()

        msg = {
            "type": "frontend_error",
            "data": {
                "message": "Unhandled Promise Rejection: NetworkError",
                "type": "UnhandledRejection",
                "stack": "Error: NetworkError\n    at fetch",
            },
        }

        _capture_frontend_error_to_log_buffer(msg)

        entries, total = await buf.list(source_filter="frontend.ws")
        assert total >= 1
        assert "NetworkError" in entries[0]["message"]
        assert entries[0]["details"]["error_type"] == "UnhandledRejection"

    @pytest.mark.asyncio
    async def test_ws_frontend_error_broadcasts(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import _capture_frontend_error_to_log_buffer

        captured = []

        def capture(event_type, data):
            captured.append((event_type, data))

        with patch.object(main_mod, "queue_broadcast", side_effect=capture):
            msg = {
                "type": "frontend_error",
                "data": {
                    "message": "broadcast check",
                    "source": "b.js",
                    "lineno": 1,
                },
            }
            _capture_frontend_error_to_log_buffer(msg)

        assert any(c[0] == "app_event" for c in captured)
        event_data = next(c[1] for c in captured if c[0] == "app_event")
        assert event_data["source"] == "frontend.ws"
        assert "broadcast check" in event_data["message"]
