import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Cookie

from ..config import settings
from ..telemetry import get_logger
from ..store.database import Database
from ..utils import get_client_ip

logger = get_logger("whatsapp.admin")


class AdminSession:
    SESSION_DURATION_HOURS = 24

    def __init__(self, db: Database):
        self._db = db
        self._session_cookie_name = "admin_session"

    def verify_password(self, password: str) -> bool:
        if not settings.admin_password:
            logger.warning("Admin password not configured")
            return False
        return hmac.compare_digest(password, settings.admin_password)

    async def create_session(
        self,
        request: Request,
        password: str,
    ) -> Optional[str]:
        if not self.verify_password(password):
            ip = get_client_ip(request)
            logger.warning(f"Failed admin login attempt from {ip}")
            return None

        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=self.SESSION_DURATION_HOURS)

        ip = get_client_ip(request)
        await self._db.create_admin_session(
            session_id=session_id,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent"),
            ip_address=ip,
        )

        logger.info(f"Admin session created for {ip}")
        return session_id

    async def validate_session(
        self,
        session_id: Optional[str],
    ) -> bool:
        if not session_id:
            return False

        session = await self._db.get_admin_session(session_id)
        if session:
            await self._refresh_session(session_id)
            return True
        return False

    async def _refresh_session(self, session_id: str) -> None:
        new_expires = datetime.now() + timedelta(hours=self.SESSION_DURATION_HOURS)
        await self._db.update_admin_session_expiry(session_id, new_expires)

    async def get_session(
        self,
        session_id: Optional[str],
    ) -> Optional[dict]:
        if not session_id:
            return None

        return await self._db.get_admin_session(session_id)

    async def logout(self, session_id: str) -> None:
        await self._db.delete_admin_session(session_id)
        logger.info("Admin session ended")


def get_session_id(
    admin_session: Optional[str] = Cookie(None, alias="admin_session"),
) -> Optional[str]:
    return admin_session


async def require_admin_session(
    request: Request,
    session_id: Optional[str] = Cookie(None, alias="admin_session"),
) -> str:
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin interface not configured")

    if not session_id:
        if request.headers.get("accept", "").startswith("text/html"):
            raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
        raise HTTPException(status_code=401, detail="Not authenticated")

    from ..tenant import tenant_manager

    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    session = await db.get_admin_session(session_id)
    if not session:
        if request.headers.get("accept", "").startswith("text/html"):
            raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
        raise HTTPException(status_code=401, detail="Session expired")

    return session_id
