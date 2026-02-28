from fastapi import Depends, HTTPException, Header, status, Request
from typing import Optional

from ..config import settings
from ..tenant import tenant_manager, Tenant
from ..middleware import rate_limiter


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    if request.client:
        return request.client.host

    return "unknown"


def get_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> str:
    ip = get_client_ip(request)

    if rate_limiter.is_blocked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Your IP has been blocked due to too many failed attempts.",
        )

    api_key = x_api_key
    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]

    if not api_key:
        rate_limiter.record_failed_auth(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Use X-API-Key header or Bearer token.",
        )
    return api_key


def get_tenant(request: Request, api_key: str = Depends(get_api_key)) -> Tenant:
    ip = get_client_ip(request)
    tenant = tenant_manager.get_tenant_by_key(api_key)
    if not tenant:
        attempts, blocked = rate_limiter.record_failed_auth(ip)
        detail = f"Invalid API key. Attempt {attempts}/{rate_limiter.max_failed_auth_attempts}"
        if blocked:
            detail = "Invalid API key. Your IP has been blocked due to too many failed attempts."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )
    rate_limiter.clear_failed_auth(ip)
    return tenant


def get_admin_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> str:
    ip = get_client_ip(request)

    if rate_limiter.is_blocked(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Your IP has been blocked due to too many failed attempts.",
        )

    api_key = x_api_key
    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]

    if not api_key:
        rate_limiter.record_failed_auth(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required",
        )

    assert api_key is not None

    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key not configured",
        )

    if api_key != settings.admin_api_key:
        attempts, blocked = rate_limiter.record_failed_auth(ip)
        detail = f"Invalid admin API key. Attempt {attempts}/{rate_limiter.max_failed_auth_attempts}"
        if blocked:
            detail = "Invalid admin API key. Your IP has been blocked due to too many failed attempts."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    rate_limiter.clear_failed_auth(ip)
    return api_key
