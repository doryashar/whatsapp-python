import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from src.tenant import Tenant, TenantManager


@pytest.fixture
def tenant():
    return Tenant(
        api_key_hash="test_hash_123",
        name="test_tenant",
        has_auth=True,
        connection_state="connected",
        creds_json={"creds": {"noiseKey": "test"}, "keys": {}},
    )


@pytest.fixture
def tenant_manager():
    return TenantManager()


class TestRestartLockPreventsConcurrentRestarts:
    @pytest.mark.asyncio
    async def test_concurrent_restart_calls_are_serialized(self, tenant):
        call_count = 0
        max_concurrent = 0
        current_concurrent = 0

        async def mock_start():
            nonlocal call_count, max_concurrent, current_concurrent
            call_count += 1
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.1)
            current_concurrent -= 1

        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = None
            mock_mgr.record_restart = Mock()
            mock_mgr.reset_health_failures = Mock()

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 0
                mock_settings.auth_dir = Path("/tmp/auth")

                with patch("src.main.BaileysBridge") as MockBridge:
                    mock_bridge_instance = Mock()
                    mock_bridge_instance.start = mock_start
                    mock_bridge_instance.stop = AsyncMock()
                    mock_bridge_instance._process = Mock()
                    mock_bridge_instance._process.pid = 12345
                    MockBridge.return_value = mock_bridge_instance

                    from src.main import _restart_bridge

                    results = await asyncio.gather(
                        _restart_bridge(tenant, "test1"),
                        _restart_bridge(tenant, "test2"),
                        _restart_bridge(tenant, "test3"),
                    )

                    successes = sum(r for r in results)
                    assert successes == 1, "Only one restart should succeed"
                    assert max_concurrent == 1, "Restarts should be serialized"
                    assert call_count == 1, "Bridge should be started exactly once"

    @pytest.mark.asyncio
    async def test_restart_flag_resets_after_completion(self, tenant):
        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = None
            mock_mgr.record_restart = Mock()
            mock_mgr.reset_health_failures = Mock()

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 0
                mock_settings.auth_dir = Path("/tmp/auth")

                with patch("src.main.BaileysBridge") as MockBridge:
                    mock_bridge_instance = Mock()
                    mock_bridge_instance.start = AsyncMock()
                    mock_bridge_instance.stop = AsyncMock()
                    mock_bridge_instance._process = Mock()
                    mock_bridge_instance._process.pid = 12345
                    MockBridge.return_value = mock_bridge_instance

                    from src.main import _restart_bridge

                    assert tenant._restarting is False
                    result = await _restart_bridge(tenant, "test")
                    assert result is True
                    assert tenant._restarting is False

    @pytest.mark.asyncio
    async def test_restart_flag_resets_on_exception(self, tenant):
        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = None
            mock_mgr.record_restart = Mock()

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 0
                mock_settings.auth_dir = Path("/tmp/auth")

                with patch("src.main.BaileysBridge") as MockBridge:
                    MockBridge.return_value = Mock(
                        stop=AsyncMock(),
                        start=AsyncMock(side_effect=RuntimeError("boom")),
                    )

                    from src.main import _restart_bridge

                    assert tenant._restarting is False
                    result = await _restart_bridge(tenant, "test")
                    assert result is False
                    assert tenant._restarting is False

    @pytest.mark.asyncio
    async def test_sequential_restarts_both_succeed(self, tenant):
        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = None
            mock_mgr.record_restart = Mock()
            mock_mgr.reset_health_failures = Mock()

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 0
                mock_settings.auth_dir = Path("/tmp/auth")

                with patch("src.main.BaileysBridge") as MockBridge:
                    mock_bridge_instance = Mock()
                    mock_bridge_instance.start = AsyncMock()
                    mock_bridge_instance.stop = AsyncMock()
                    mock_bridge_instance._process = Mock()
                    mock_bridge_instance._process.pid = 12345
                    MockBridge.return_value = mock_bridge_instance

                    from src.main import _restart_bridge

                    result1 = await _restart_bridge(tenant, "test1")
                    assert result1 is True

                    result2 = await _restart_bridge(tenant, "test2")
                    assert result2 is True

    @pytest.mark.asyncio
    async def test_record_restart_called_before_await_points(self, tenant):
        call_order = []

        def track_record(t, reason):
            call_order.append("record_restart")

        original_sleep = asyncio.sleep

        async def tracked_sleep(seconds):
            call_order.append(f"sleep({seconds})")
            await original_sleep(0)

        with patch("src.main.tenant_manager") as mock_mgr:
            mock_mgr.can_restart = Mock(return_value=True)
            mock_mgr._event_handler = None
            mock_mgr.record_restart = Mock(side_effect=track_record)
            mock_mgr.reset_health_failures = Mock()

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 1
                mock_settings.auth_dir = Path("/tmp/auth")

                async def fake_start():
                    call_order.append("bridge_start")
                    await asyncio.sleep(0)

                with patch("src.main.BaileysBridge") as MockBridge:
                    mock_bridge_instance = Mock()
                    mock_bridge_instance.start = fake_start
                    mock_bridge_instance.stop = AsyncMock()
                    mock_bridge_instance._process = Mock()
                    mock_bridge_instance._process.pid = 12345
                    MockBridge.return_value = mock_bridge_instance

                    with patch("src.main.asyncio.sleep", side_effect=tracked_sleep):
                        from src.main import _restart_bridge

                        await _restart_bridge(tenant, "test")

                        assert call_order[0] == "record_restart", (
                            f"record_restart should be called first, got: {call_order}"
                        )
                        assert call_order[1] == "sleep(1)"
                        assert call_order[2] == "bridge_start"


class TestClearCredsDeletesFilesystem:
    @pytest.mark.asyncio
    async def test_clear_creds_removes_auth_directory(self, tenant):
        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TenantManager()
            tm._base_auth_dir = Path(tmpdir)

            auth_dir = tenant.get_auth_dir(tm._base_auth_dir)
            auth_dir.mkdir(parents=True, exist_ok=True)
            (auth_dir / "creds.json").write_text('{"noiseKey": "test"}')
            keys_dir = auth_dir / "keys"
            keys_dir.mkdir(exist_ok=True)
            (keys_dir / "key1").write_text("secret")

            assert auth_dir.exists()

            with patch.object(tm, "_db") as mock_db:
                mock_db.clear_creds = AsyncMock()
                await tm.clear_creds(tenant)

            assert not auth_dir.exists(), "Auth directory should be deleted"
            assert tenant.creds_json is None
            assert tenant.has_auth is False
            mock_db.clear_creds.assert_called_once_with(tenant.api_key_hash)

    @pytest.mark.asyncio
    async def test_clear_creds_handles_missing_directory(self, tenant):
        tm = TenantManager()
        tm._base_auth_dir = Path("/tmp/nonexistent_test_dir_clear")

        with patch.object(tm, "_db") as mock_db:
            mock_db.clear_creds = AsyncMock()
            await tm.clear_creds(tenant)

        assert tenant.creds_json is None
        assert tenant.has_auth is False


class TestClearCredsStopsBridge:
    @pytest.mark.asyncio
    async def test_admin_clear_credentials_stops_bridge(self):
        tenant = Tenant(
            api_key_hash="test_hash_clear",
            name="clear_test",
            has_auth=True,
            connection_state="connected",
        )
        mock_bridge = Mock()
        mock_bridge.stop = AsyncMock()
        tenant.bridge = mock_bridge

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}
            mock_mgr.clear_creds = AsyncMock()

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                from src.admin.routes import clear_tenant_credentials

                result = await clear_tenant_credentials(tenant.api_key_hash, "session")

                assert result["status"] == "credentials_cleared"
                mock_bridge.stop.assert_called_once()
                assert tenant.bridge is None
                assert tenant.connection_state == "disconnected"
                mock_mgr.clear_creds.assert_called_once_with(tenant)

    @pytest.mark.asyncio
    async def test_admin_clear_credentials_no_bridge(self):
        tenant = Tenant(
            api_key_hash="test_hash_no_bridge",
            name="no_bridge_test",
            has_auth=True,
            connection_state="connected",
        )
        tenant.bridge = None

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}
            mock_mgr.clear_creds = AsyncMock()

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                from src.admin.routes import clear_tenant_credentials

                result = await clear_tenant_credentials(tenant.api_key_hash, "session")

                assert result["status"] == "credentials_cleared"
                assert tenant.connection_state == "disconnected"
                mock_mgr.clear_creds.assert_called_once_with(tenant)


class TestReconnectGuard:
    @pytest.mark.asyncio
    async def test_reconnect_rejected_when_restarting(self):
        from fastapi import HTTPException

        tenant = Tenant(
            api_key_hash="test_hash_reconnect",
            name="reconnect_test",
            has_auth=True,
        )
        tenant._restarting = True

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                from src.admin.routes import reconnect_tenant

                with pytest.raises(HTTPException) as exc_info:
                    await reconnect_tenant(tenant.api_key_hash, "session")

                assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_reconnect_succeeds_when_not_restarting(self):
        tenant = Tenant(
            api_key_hash="test_hash_ok_reconnect",
            name="ok_reconnect_test",
            has_auth=True,
        )
        tenant._restarting = False
        tenant.bridge = None

        mock_bridge = Mock()
        mock_bridge.login = AsyncMock(return_value={"status": "connecting"})

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}
            mock_mgr.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                from src.admin.routes import reconnect_tenant

                result = await reconnect_tenant(tenant.api_key_hash, "session")

                assert result["status"] == "reconnecting"


class TestNoNodeJsAutoReconnect:
    def test_nodejs_disconnect_handler_exists(self):
        with open("bridge/index.mjs") as f:
            content = f.read()

        assert 'sendEvent("disconnected"' in content, (
            "Node.js should still send disconnected event to Python"
        )

        section = content.split('sendEvent("disconnected"')[1].split(
            "if (statusCode === DisconnectReason.loggedOut)"
        )[0]
        assert "setTimeout" not in section, (
            "Node.js should NOT have setTimeout auto-reconnect between disconnected event and loggedOut check"
        )
