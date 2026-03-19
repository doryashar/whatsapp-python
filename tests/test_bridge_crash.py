import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestHandleBridgeCrash:
    @pytest.mark.asyncio
    async def test_handle_bridge_crash_success_no_duplicate_state_update(self):
        from src.main import handle_bridge_crash

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.bridge = MagicMock()
        tenant.bridge._process = MagicMock()
        tenant.bridge._process.returncode = 1
        tenant.has_valid_auth = MagicMock(return_value=True)
        tenant._restarting = False
        tenant._restart_lock = asyncio.Lock()

        with patch("src.main.tenant_manager") as mock_manager:
            mock_manager.can_restart = MagicMock(return_value=True)
            mock_manager.update_session_state = AsyncMock()
            mock_manager.record_restart = MagicMock()
            mock_manager.reset_health_failures = MagicMock()
            mock_manager._event_handler = None

            with patch("src.main.settings") as mock_settings:
                mock_settings.restart_cooldown_seconds = 0
                mock_settings.auth_dir = "/tmp/auth"

                with patch("src.main.BaileysBridge") as MockBridge:
                    mock_bridge = AsyncMock()
                    mock_bridge.start = AsyncMock()
                    mock_bridge._process = MagicMock()
                    mock_bridge._process.pid = 12345
                    MockBridge.return_value = mock_bridge

                    await handle_bridge_crash(tenant)

                    mock_manager.update_session_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_bridge_crash_failure_sets_disconnected(self):
        from src.main import handle_bridge_crash

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.bridge = MagicMock()
        tenant.bridge._process = MagicMock()
        tenant.bridge._process.returncode = 1
        tenant.has_valid_auth = MagicMock(return_value=False)

        with patch("src.main.tenant_manager") as mock_manager:
            mock_manager.update_session_state = AsyncMock()

            await handle_bridge_crash(tenant)

            mock_manager.update_session_state.assert_called_once_with(
                tenant, "disconnected"
            )

    @pytest.mark.asyncio
    async def test_handle_bridge_crash_no_auth_sets_disconnected(self):
        from src.main import handle_bridge_crash

        tenant = MagicMock()
        tenant.name = "test_tenant"
        tenant.bridge = MagicMock()
        tenant.bridge._process = MagicMock()
        tenant.bridge._process.returncode = 1
        tenant.has_valid_auth = MagicMock(return_value=False)

        with patch("src.main.tenant_manager") as mock_manager:
            mock_manager.update_session_state = AsyncMock()

            await handle_bridge_crash(tenant)

            mock_manager.update_session_state.assert_called_once_with(
                tenant, "disconnected"
            )
