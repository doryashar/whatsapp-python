import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, UTC
from src.admin.auth import AdminSession, get_session_id, require_admin_session
from src.config import settings


class TestAdminSession:
    def test_verify_password_correct(self):
        db = MagicMock()
        session = AdminSession(db)
        assert session.verify_password("test-admin-password-123") is True

    def test_verify_password_incorrect(self):
        db = MagicMock()
        session = AdminSession(db)
        assert session.verify_password("wrong-password") is False

    def test_verify_password_no_config(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "")
        db = MagicMock()
        session = AdminSession(db)
        assert session.verify_password("anything") is False

    @pytest.mark.asyncio
    async def test_create_session_success(self):
        db = MagicMock()
        db.create_admin_session = AsyncMock()
        db.delete_admin_session = AsyncMock()
        request = MagicMock()
        request.headers = {"user-agent": "test-agent"}
        session = AdminSession(db)
        with patch("src.admin.auth.get_client_ip", return_value="127.0.0.1"):
            result = await session.create_session(request, "test-admin-password-123")
        assert result is not None
        assert len(result) > 0
        db.create_admin_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_wrong_password(self):
        db = MagicMock()
        request = MagicMock()
        session = AdminSession(db)
        with patch("src.admin.auth.get_client_ip", return_value="127.0.0.1"):
            result = await session.create_session(request, "wrong-password")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_session_replaces_existing(self):
        db = MagicMock()
        db.create_admin_session = AsyncMock()
        db.delete_admin_session = AsyncMock()
        request = MagicMock()
        request.headers = {"user-agent": "test-agent"}
        session = AdminSession(db)
        with patch("src.admin.auth.get_client_ip", return_value="127.0.0.1"):
            result = await session.create_session(
                request, "test-admin-password-123", existing_session_id="old-session"
            )
        assert result is not None
        db.delete_admin_session.assert_called_once_with("old-session")

    @pytest.mark.asyncio
    async def test_validate_session_valid(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value={"session_id": "test123"})
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        result = await session.validate_session("test123")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_session_invalid(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value=None)
        session = AdminSession(db)
        result = await session.validate_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_session_none(self):
        db = MagicMock()
        session = AdminSession(db)
        result = await session.validate_session(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_session_valid(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(
            return_value={
                "session_id": "test123",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        )
        session = AdminSession(db)
        result = await session.get_session("test123")
        assert result is not None
        assert result["session_id"] == "test123"

    @pytest.mark.asyncio
    async def test_get_session_none(self):
        db = MagicMock()
        session = AdminSession(db)
        result = await session.get_session(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_missing(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value=None)
        session = AdminSession(db)
        result = await session.get_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_logout(self):
        db = MagicMock()
        db.delete_admin_session = AsyncMock()
        session = AdminSession(db)
        await session.logout("session123")
        db.delete_admin_session.assert_called_once_with("session123")

    @pytest.mark.asyncio
    async def test_refresh_session_when_remaining(self):
        db = MagicMock()
        future_time = datetime.now(UTC) + timedelta(hours=20)
        db.get_admin_session = AsyncMock(
            return_value={"expires_at": future_time.isoformat()}
        )
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        await session._refresh_session("test123")
        db.update_admin_session_expiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_session_when_low(self):
        db = MagicMock()
        near_expiry = datetime.now(UTC) + timedelta(hours=2)
        db.get_admin_session = AsyncMock(
            return_value={"expires_at": near_expiry.isoformat()}
        )
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        await session._refresh_session("test123")
        db.update_admin_session_expiry.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_session_nonexistent(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value=None)
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        await session._refresh_session("nonexistent")
        db.update_admin_session_expiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_session_invalid_expiry_format(self):
        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value={"expires_at": "not-a-date"})
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        await session._refresh_session("test123")
        db.update_admin_session_expiry.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_session_naive_datetime(self):
        db = MagicMock()
        near_expiry = datetime.now(UTC) + timedelta(hours=2)
        naive = near_expiry.replace(tzinfo=None)
        db.get_admin_session = AsyncMock(return_value={"expires_at": naive.isoformat()})
        db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(db)
        await session._refresh_session("test123")
        db.update_admin_session_expiry.assert_called_once()


class TestGetSessionId:
    def test_returns_session_cookie(self):
        result = get_session_id(admin_session="session-abc")
        assert result == "session-abc"

    def test_returns_none(self):
        result = get_session_id(admin_session=None)
        assert result is None


class TestRequireAdminSession:
    @pytest.mark.asyncio
    async def test_no_password_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "")
        request = MagicMock()
        request.headers = {"accept": "application/json"}
        with pytest.raises(Exception):
            await require_admin_session(request, session_id=None)

    @pytest.mark.asyncio
    async def test_no_session_html_redirect(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        request = MagicMock()
        request.headers = {"accept": "text/html"}
        with pytest.raises(Exception):
            await require_admin_session(request, session_id=None)

    @pytest.mark.asyncio
    async def test_no_session_api_401(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        request = MagicMock()
        request.headers = {"accept": "application/json"}
        with pytest.raises(Exception):
            await require_admin_session(request, session_id=None)

    @pytest.mark.asyncio
    async def test_no_database(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        from src.tenant import tenant_manager

        original_db = tenant_manager._db
        tenant_manager._db = None
        request = MagicMock()
        request.headers = {"accept": "application/json"}
        try:
            with pytest.raises(Exception):
                await require_admin_session(request, session_id="test123")
        finally:
            tenant_manager._db = original_db

    @pytest.mark.asyncio
    async def test_expired_session_html_redirect(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        from src.tenant import tenant_manager

        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value=None)
        original_db = tenant_manager._db
        tenant_manager._db = db
        request = MagicMock()
        request.headers = {"accept": "text/html"}
        try:
            with pytest.raises(Exception):
                await require_admin_session(request, session_id="expired")
        finally:
            tenant_manager._db = original_db

    @pytest.mark.asyncio
    async def test_expired_session_api_401(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        from src.tenant import tenant_manager

        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value=None)
        original_db = tenant_manager._db
        tenant_manager._db = db
        request = MagicMock()
        request.headers = {"accept": "application/json"}
        try:
            with pytest.raises(Exception):
                await require_admin_session(request, session_id="expired")
        finally:
            tenant_manager._db = original_db

    @pytest.mark.asyncio
    async def test_valid_session(self, monkeypatch):
        monkeypatch.setattr(settings, "admin_password", "password")
        from src.tenant import tenant_manager

        db = MagicMock()
        db.get_admin_session = AsyncMock(return_value={"session_id": "valid123"})
        db.update_admin_session_expiry = AsyncMock()
        original_db = tenant_manager._db
        tenant_manager._db = db
        request = MagicMock()
        request.headers = {"accept": "application/json"}
        try:
            result = await require_admin_session(request, session_id="valid123")
            assert result == "valid123"
        finally:
            tenant_manager._db = original_db
