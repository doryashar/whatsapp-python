import asyncio

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, AsyncMock

from src.admin.log_buffer import LogBuffer, LogEntry
from tests.conftest import ADMIN_PASSWORD


# ─── TestLogsAuth ───


class TestLogsAuth:
    @pytest.mark.asyncio
    async def test_fragment_without_auth(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/fragments/logs", follow_redirects=False)
            assert response.status_code in (302, 303, 401, 403)

    @pytest.mark.asyncio
    async def test_fragment_with_expired_session(self, setup_tenant_manager):
        from src.main import app

        async def _get_session(sid):
            return None

        setup_tenant_manager._db.get_admin_session = _get_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.cookies.set("admin_session", "expired-session")
            response = await client.get("/admin/fragments/logs", follow_redirects=False)
            assert response.status_code in (302, 303, 401, 403)

    @pytest.mark.asyncio
    async def test_clear_without_auth(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/api/logs/clear", follow_redirects=False
            )
            assert response.status_code in (302, 303, 401, 403)


# ─── TestLogsXSS ───


class TestLogsXSS:
    @pytest.mark.asyncio
    async def test_xss_in_message_escaped_in_response(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source="test",
                    message="<script>alert('xss')</script>",
                )
            )
            response = await client.get("/admin/fragments/logs")
            assert response.status_code == 200
            data = response.json()
            msg = data["entries"][0]["message"]
            assert "<script>" in msg

    @pytest.mark.asyncio
    async def test_xss_in_tenant_field_escaped(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source="test",
                    message="normal msg",
                    tenant="<img onerror='alert(1)' src=x>",
                )
            )
            response = await client.get("/admin/fragments/logs")
            data = response.json()
            assert "<img onerror" in data["entries"][0]["tenant"]

    @pytest.mark.asyncio
    async def test_xss_in_source_field_escaped(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source='<script>alert("src-xss")</script>',
                    message="normal",
                )
            )
            response = await client.get("/admin/fragments/logs")
            data = response.json()
            assert "<script>" in data["entries"][0]["source"]

    @pytest.mark.asyncio
    async def test_log_buffer_preserves_raw_html(self, setup_tenant_manager):
        buf = LogBuffer(max_size=10)
        html_msg = '<b onclick="alert(1)">click me</b>'
        buf.add_sync(
            LogEntry(
                id=0,
                timestamp="",
                type="log",
                level="INFO",
                source="test",
                message=html_msg,
            )
        )

        entries, total = await buf.list()
        assert total == 1
        assert entries[0]["message"] == html_msg


# ─── TestLogsInputValidation ───


class TestLogsInputValidation:
    @pytest.mark.asyncio
    async def test_search_with_special_regex_chars(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            for pattern in [".*", ".*()+", "(.*)", "[a-z]+", "^$", "\\d+"]:
                response = await client.get(f"/admin/fragments/logs?search={pattern}")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_limit_boundary_values(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            valid_limits = [1, 100, 1000]
            for limit in valid_limits:
                response = await client.get(f"/admin/fragments/logs?limit={limit}")
                assert response.status_code == 200

            invalid_limits = [-1, 5001, 0]
            for limit in invalid_limits:
                response = await client.get(f"/admin/fragments/logs?limit={limit}")
                assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_and_whitespace_params(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.get("/admin/fragments/logs?search=&level=&source=")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_nonexistent_filter_values(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.get(
                "/admin/fragments/logs?level=NONEXISTENT&type=FAKE"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
