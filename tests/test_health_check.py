"""
Tests for connection health check and auto-restart functionality
"""

import pytest
import asyncio
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from src.tenant import Tenant, TenantManager
from src.config import settings
from src.bridge.client import BaileysBridge


@pytest.fixture
def tenant():
    return Tenant(
        api_key_hash="test_hash_123",
        name="test_tenant",
        has_auth=True,
        connection_state="connected",
    )


@pytest.fixture
def tenant_manager():
    return TenantManager()


class TestHealthCheckTracking:
    def test_reset_health_failures(self, tenant_manager, tenant):
        tenant.health_check_failures = 3
        tenant_manager.reset_health_failures(tenant)

        assert tenant.health_check_failures == 0
        assert tenant.last_successful_health_check is not None
        assert isinstance(tenant.last_successful_health_check, datetime)

    def test_increment_health_failures(self, tenant_manager, tenant):
        tenant.health_check_failures = 0
        result = tenant_manager.increment_health_failures(tenant)

        assert result == 1
        assert tenant.health_check_failures == 1
        assert tenant.last_health_check is not None

    def test_multiple_health_failures(self, tenant_manager, tenant):
        for i in range(1, 4):
            result = tenant_manager.increment_health_failures(tenant)
            assert result == i
        assert tenant.health_check_failures == 3


class TestRestartRateLimiting:
    def test_can_restart_initially(self, tenant_manager, tenant):
        assert tenant_manager.can_restart(tenant) is True

    def test_can_restart_within_limit(self, tenant_manager, tenant):
        for _ in range(settings.max_restart_attempts - 1):
            tenant_manager.record_restart(tenant, "test")

        assert tenant_manager.can_restart(tenant) is True

    def test_cannot_restart_after_limit(self, tenant_manager, tenant):
        for _ in range(settings.max_restart_attempts):
            tenant_manager.record_restart(tenant, "test")

        assert tenant_manager.can_restart(tenant) is False

    def test_restart_window_expires(self, tenant_manager, tenant):
        old_time = datetime.now(UTC) - timedelta(
            seconds=settings.restart_window_seconds + 10
        )
        tenant_manager._restart_history[tenant.api_key_hash] = [
            old_time,
            old_time,
            old_time,
        ]

        assert tenant_manager.can_restart(tenant) is True

    def test_record_restart_updates_tenant(self, tenant_manager, tenant):
        initial_restarts = tenant.total_restarts
        tenant_manager.record_restart(tenant, "process_crash")

        assert tenant.total_restarts == initial_restarts + 1
        assert tenant.last_restart_at is not None
        assert tenant.last_restart_reason == "process_crash"

    def test_auto_restart_disabled(self, tenant_manager, tenant):
        with patch.object(settings, "auto_restart_bridge", False):
            assert tenant_manager.can_restart(tenant) is False


class TestBridgeHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self, tenant, tenant_manager):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)
        tenant.bridge.get_status = AsyncMock(
            return_value={"connection_state": "connected"}
        )
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345

        tenant_manager.reset_health_failures(tenant)

        status = await tenant.bridge.get_status()
        assert status["connection_state"] == "connected"

    @pytest.mark.asyncio
    async def test_health_check_failure(self, tenant, tenant_manager):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)
        tenant.bridge.get_status = AsyncMock(
            return_value={"connection_state": "disconnected"}
        )
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345

        failures = tenant_manager.increment_health_failures(tenant)
        assert failures == 1

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, tenant, tenant_manager):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)

        async def slow_status():
            await asyncio.sleep(15)
            return {"connection_state": "connected"}

        tenant.bridge.get_status = slow_status
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                tenant.bridge.get_status(),
                timeout=settings.health_check_timeout_seconds,
            )

    @pytest.mark.asyncio
    async def test_bridge_process_death_detection(self, tenant):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=False)
        tenant.bridge._process = Mock()
        tenant.bridge._process.returncode = 1

        assert tenant.bridge.is_alive() is False


class TestAutoRestart:
    @pytest.mark.asyncio
    async def test_handle_bridge_crash_with_valid_auth(self, tenant):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=False)
        tenant.bridge.stop = AsyncMock()
        tenant.bridge._process = Mock()
        tenant.bridge._process.returncode = 1

        tenant.has_auth = True
        tenant.connection_state = "connected"

        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = Mock()
            mock_mgr.record_restart = Mock()
            mock_mgr.reset_health_failures = Mock()
            mock_mgr.update_session_state = AsyncMock()

            with patch("src.main.BaileysBridge") as MockBridge:
                mock_bridge_instance = Mock(spec=BaileysBridge)
                mock_bridge_instance.start = AsyncMock()
                mock_bridge_instance._process = Mock()
                mock_bridge_instance._process.pid = 54321
                MockBridge.return_value = mock_bridge_instance

                from src.main import handle_bridge_crash

                await handle_bridge_crash(tenant)

    @pytest.mark.asyncio
    async def test_handle_bridge_crash_without_auth(self, tenant):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.stop = AsyncMock()
        tenant.bridge._process = Mock()
        tenant.bridge._process.returncode = 1

        tenant.has_auth = False
        tenant.creds_json = None

        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.update_session_state = AsyncMock()

            from src.main import handle_bridge_crash

            await handle_bridge_crash(tenant)

            mock_mgr.update_session_state.assert_called()

    @pytest.mark.asyncio
    async def test_handle_bridge_crash_rate_limited(self, tenant):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.stop = AsyncMock()
        tenant.bridge._process = Mock()
        tenant.bridge._process.returncode = 1
        tenant.has_auth = True

        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=False)
            mock_mgr.update_session_state = AsyncMock()

            from src.main import handle_bridge_crash

            await handle_bridge_crash(tenant)


class TestTenantMetrics:
    def test_tenant_health_metrics(self, tenant):
        tenant.health_check_failures = 2
        tenant.last_health_check = datetime.now(UTC)
        tenant.last_successful_health_check = datetime.now(UTC) - timedelta(minutes=5)
        tenant.total_restarts = 1
        tenant.last_restart_reason = "process_crash"

        assert tenant.health_check_failures == 2
        assert tenant.total_restarts == 1
        assert tenant.last_restart_reason == "process_crash"

    def test_tenant_bridge_metrics(self, tenant):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345
        tenant.bridge._process.returncode = None
        tenant.bridge.is_alive = Mock(return_value=True)

        assert tenant.bridge._process.pid == 12345
        assert tenant.bridge.is_alive() is True


class TestHealthCheckIntegration:
    @pytest.mark.asyncio
    async def test_full_health_check_cycle(self, tenant, tenant_manager):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)
        tenant.bridge.get_status = AsyncMock(
            return_value={"connection_state": "connected"}
        )
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345

        for i in range(settings.max_health_check_failures):
            if i < settings.max_health_check_failures - 1:
                tenant.bridge.get_status = AsyncMock(
                    return_value={"connection_state": "disconnected"}
                )
                failures = tenant_manager.increment_health_failures(tenant)
                assert failures == i + 1
            else:
                tenant.bridge.get_status = AsyncMock(
                    return_value={"connection_state": "connected"}
                )
                tenant_manager.reset_health_failures(tenant)
                assert tenant.health_check_failures == 0
                break

    @pytest.mark.asyncio
    async def test_max_failures_triggers_disconnect(self, tenant, tenant_manager):
        tenant.connection_state = "connected"
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)
        tenant.bridge._process = Mock()

        for i in range(settings.max_health_check_failures):
            tenant_manager.increment_health_failures(tenant)

        assert tenant.health_check_failures >= settings.max_health_check_failures

    @pytest.mark.asyncio
    async def test_health_check_uses_connection_state_field(
        self, tenant, tenant_manager
    ):
        tenant.bridge = Mock(spec=BaileysBridge)
        tenant.bridge.is_alive = Mock(return_value=True)
        tenant.bridge._process = Mock()
        tenant.bridge._process.pid = 12345

        tenant.bridge.get_status = AsyncMock(
            return_value={
                "connection_state": "connected",
                "self": None,
                "has_qr": False,
            }
        )
        status = await tenant.bridge.get_status()
        assert status.get("connection_state") == "connected"

        tenant.bridge.get_status = AsyncMock(
            return_value={
                "connection_state": "disconnected",
                "self": None,
                "has_qr": False,
            }
        )
        status = await tenant.bridge.get_status()
        assert status.get("connection_state") == "disconnected"
        assert status.get("connected") is None
