import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Cookie
from fastapi.responses import RedirectResponse

from ..config import settings
from ..telemetry import get_logger
from ..store.database import Database

logger = get_logger("whatsapp.admin")


class AdminSession:
    def __init__(self, db: Database):
        self._db = db
        self._session_cookie_name = "admin_session"

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        if not settings.admin_password:
            logger.warning("Admin password not configured")
            return False
        return password == settings.admin_password

    async def create_session(
        self,
        request: Request,
        password: str,
    ) -> Optional[str]:
        if not self.verify_password(password):
            logger.warning(
                f"Failed admin login attempt from {request.client.host if request.client else 'unknown'}"
            )
            return None

        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        await self._db.create_admin_session(
            session_id=session_id,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )

        logger.info(
            f"Admin session created for {request.client.host if request.client else 'unknown'}"
        )
        return session_id

    async def validate_session(
        self,
        session_id: Optional[str],
    ) -> bool:
        if not session_id:
            return False

        session = await self._db.get_admin_session(session_id)
        return session is not None

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
