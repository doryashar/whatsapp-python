import logging

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
import asyncio

from src.admin.log_buffer import LogEntry
from tests.conftest import ADMIN_PASSWORD


def _seed_buffer(buf, count=20):
    for i in range(count):
        buf.add_sync(
            LogEntry(
                id=0,
                timestamp=f"2026-01-01T00:0{i % 10}:00+00:00",
                type="log" if i % 3 != 0 else "event",
                level=["INFO", "ERROR", "WARNING", "DEBUG", "EVENT"][i % 5],
                source=f"whatsapp.{['bridge', 'admin', 'api', 'database'][i % 4]}",
                message=f"test log message {i}",
                tenant="TestTenant" if i % 5 == 0 else "",
                details={},
            )
        )


# ─── TestLogsPage ───


class TestLogsPage:
    @pytest.mark.asyncio
    async def test_logs_page_renders(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.get("/admin/logs")
            assert response.status_code == 200
            html = response.text
            assert "Logs" in html
            assert "log-search" in html
            assert "log-type-filter" in html
            assert "log-level-filter" in html
            assert "log-source-filter" in html
            assert "log-stream" in html
            assert "pause-btn" in html
            assert "events-btn" in html

    @pytest.mark.asyncio
    async def test_logs_page_requires_auth(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/logs", follow_redirects=False)
            assert response.status_code in (302, 303, 401)

    @pytest.mark.asyncio
    async def test_logs_page_invalid_session(self, setup_tenant_manager):
        from src.main import app

        async def _get_session(sid):
            if sid == "invalid-session":
                return None
            return {
                "id": "test-session-id",
                "expires_at": "2099-01-01",
                "user_agent": "test",
                "ip_address": "127.0.0.1",
            }

        setup_tenant_manager._db.get_admin_session = _get_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.cookies.set("admin_session", "invalid-session")
            response = await client.get("/admin/logs", follow_redirects=False)
            assert response.status_code in (302, 303, 401)


# ─── TestLogsFragmentEndpoint ───


class TestLogsFragmentEndpoint:
    @pytest.mark.asyncio
    async def test_fragment_default_params(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs")
            assert response.status_code == 200
            data = response.json()
            assert "entries" in data
            assert "total" in data
            assert "max_size" in data
            assert data["total"] == 20

    @pytest.mark.asyncio
    async def test_fragment_type_filter(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs?type=log")
            assert response.status_code == 200
            data = response.json()
            assert all(e["type"] == "log" for e in data["entries"])
            assert data["total"] < 20

    @pytest.mark.asyncio
    async def test_fragment_level_filter(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs?level=ERROR")
            assert response.status_code == 200
            data = response.json()
            assert all(e["level"] == "ERROR" for e in data["entries"])

    @pytest.mark.asyncio
    async def test_fragment_source_filter(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs?source=admin")
            assert response.status_code == 200
            data = response.json()
            assert all("admin" in e["source"] for e in data["entries"])

    @pytest.mark.asyncio
    async def test_fragment_search(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs?search=message+5")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1
            assert "5" in data["entries"][0]["message"]

    @pytest.mark.asyncio
    async def test_fragment_limit(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            _seed_buffer(buf, 20)
            response = await client.get("/admin/fragments/logs?limit=1")
            assert response.status_code == 200
            data = response.json()
            assert len(data["entries"]) == 1
            assert data["total"] == 20

    @pytest.mark.asyncio
    async def test_fragment_limit_zero(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.get("/admin/fragments/logs?limit=0")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_fragment_limit_too_large(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.get("/admin/fragments/logs?limit=5000")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_fragment_empty_buffer(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            response = await client.get("/admin/fragments/logs")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data["entries"], list)


# ─── TestLogsClearEndpoint ───


class TestLogsClearEndpoint:
    @pytest.mark.asyncio
    async def test_clear_with_entries(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            _seed_buffer(buf, 20)
            response = await client.post("/admin/api/logs/clear")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cleared"
            assert data["removed"] > 0

    @pytest.mark.asyncio
    async def test_clear_empty(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await buf.clear()
            response = await client.post("/admin/api/logs/clear")
            assert response.status_code == 200
            assert response.json()["removed"] == 0

    @pytest.mark.asyncio
    async def test_clear_requires_auth(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/api/logs/clear", follow_redirects=False
            )
            assert response.status_code in (302, 303, 401)

    @pytest.mark.asyncio
    async def test_clear_twice(self, setup_tenant_manager):
        import src.main as main_mod
        from src.main import app

        buf = main_mod.log_buffer_inst

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            _seed_buffer(buf, 20)
            response1 = await client.post("/admin/api/logs/clear")
            assert response1.json()["removed"] > 0

            response2 = await client.post("/admin/api/logs/clear")
            assert response2.json()["removed"] == 0


# ─── TestLogsBufferIntegration ───


class TestLogsBufferIntegration:
    @pytest.mark.asyncio
    async def test_logger_writes_to_buffer(self, setup_tenant_manager):
        import src.main as main_mod
        from src.telemetry import get_logger

        await main_mod.log_buffer_inst.clear()
        logger = get_logger("whatsapp.test_integration")
        logger.info("buffer integration test message")

        entries, total = await main_mod.log_buffer_inst.list(
            search="buffer integration test"
        )
        assert total >= 1
        assert any("buffer integration test" in e["message"] for e in entries)

    @pytest.mark.asyncio
    async def test_different_log_levels_captured(self, setup_tenant_manager):
        import src.main as main_mod
        from src.telemetry import get_logger

        await main_mod.log_buffer_inst.clear()
        logger = get_logger("whatsapp.test_levels")
        logger.setLevel(logging.DEBUG)
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")

        entries, total = await main_mod.log_buffer_inst.list()
        levels = [e["level"] for e in entries]
        assert "DEBUG" in levels
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels

    @pytest.mark.asyncio
    async def test_log_with_tenant_extra(self, setup_tenant_manager):
        import src.main as main_mod
        from src.telemetry import get_logger

        await main_mod.log_buffer_inst.clear()
        logger = get_logger("whatsapp.test_tenant")
        logger.info("tenant test", extra={"tenant": "MyTestTenant"})

        entries, total = await main_mod.log_buffer_inst.list(search="tenant test")
        assert total >= 1
        assert any(e["tenant"] == "MyTestTenant" for e in entries)

    @pytest.mark.asyncio
    async def test_buffer_max_size_enforced(self, setup_tenant_manager):
        import src.main as main_mod
        from src.telemetry import get_logger

        max_size = main_mod.log_buffer_inst.max_size
        logger = get_logger("whatsapp.test_overflow")
        for i in range(max_size + 50):
            logger.info(f"overflow-{i}")

        size = await main_mod.log_buffer_inst.size()
        assert size <= max_size
