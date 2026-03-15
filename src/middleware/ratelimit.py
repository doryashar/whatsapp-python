import time
from collections import defaultdict
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..telemetry import get_logger
from ..utils.network import get_client_ip

logger = get_logger("whatsapp.ratelimit")


class RateLimiter:
    CLEANUP_INTERVAL = 100
    CLEANUP_CUTOFF_HOURS = 1

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        block_duration_minutes: int = 15,
        max_failed_auth_attempts: int = 5,
        failed_auth_window_minutes: int = 15,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.block_duration_seconds = block_duration_minutes * 60
        self.max_failed_auth_attempts = max_failed_auth_attempts
        self.failed_auth_window_seconds = failed_auth_window_minutes * 60

        self._minute_requests: dict[str, list[float]] = defaultdict(list)
        self._hour_requests: dict[str, list[float]] = defaultdict(list)
        self._blocked_ips: dict[str, dict] = {}
        self._failed_auth_attempts: dict[str, list[float]] = defaultdict(list)
        self._request_count = 0

    def is_blocked(self, ip: str) -> bool:
        if ip in self._blocked_ips:
            block_info = self._blocked_ips[ip]
            if time.time() - block_info["blocked_at"] > self.block_duration_seconds:
                del self._blocked_ips[ip]
                self._failed_auth_attempts.pop(ip, None)
                logger.info(f"IP unblocked after cooldown", extra={"ip": ip})
                return False
            return True
        return False

    def block_ip(self, ip: str, reason: str = "rate_limit") -> None:
        self._blocked_ips[ip] = {
            "blocked_at": time.time(),
            "reason": reason,
        }
        logger.warning(f"IP blocked", extra={"ip": ip, "reason": reason})

        # Broadcast security event to admin dashboard
        try:
            import asyncio
            from ..admin import admin_ws_manager

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    admin_ws_manager.broadcast(
                        "security_event",
                        {
                            "event": "ip_blocked",
                            "ip": ip,
                            "reason": reason,
                        },
                    )
                )
        except Exception as e:
            logger.debug(f"Failed to broadcast security event: {e}")

    def unblock_ip(self, ip: str) -> bool:
        if ip in self._blocked_ips:
            del self._blocked_ips[ip]
            self._failed_auth_attempts.pop(ip, None)
            logger.info(f"IP manually unblocked", extra={"ip": ip})
            return True
        return False

    def get_blocked_ips(self) -> list[dict]:
        now = time.time()
        return [
            {
                "ip": ip,
                "blocked_at": info["blocked_at"],
                "reason": info.get("reason", "unknown"),
                "remaining_seconds": max(
                    0, self.block_duration_seconds - (now - info["blocked_at"])
                ),
            }
            for ip, info in self._blocked_ips.items()
            if now - info["blocked_at"] <= self.block_duration_seconds
        ]

    def record_failed_auth(self, ip: str) -> tuple[int, bool]:
        now = time.time()
        window_start = now - self.failed_auth_window_seconds

        self._failed_auth_attempts[ip] = [
            t for t in self._failed_auth_attempts[ip] if t > window_start
        ]
        self._failed_auth_attempts[ip].append(now)

        attempt_count = len(self._failed_auth_attempts[ip])
        blocked = False

        if attempt_count >= self.max_failed_auth_attempts:
            self.block_ip(ip, f"failed_auth:{attempt_count}")
            blocked = True
            logger.warning(
                f"IP auto-blocked after failed auth attempts",
                extra={"ip": ip, "attempts": attempt_count},
            )
        else:
            logger.info(
                f"Failed auth attempt recorded",
                extra={
                    "ip": ip,
                    "attempts": attempt_count,
                    "max": self.max_failed_auth_attempts,
                },
            )

        return attempt_count, blocked

    def clear_failed_auth(self, ip: Optional[str] = None) -> None:
        if ip is None:
            self._failed_auth_attempts.clear()
            logger.debug("All failed auth attempts cleared")
        elif ip in self._failed_auth_attempts:
            del self._failed_auth_attempts[ip]
            logger.debug(f"Failed auth attempts cleared for IP", extra={"ip": ip})

    def get_failed_auth_attempts(self, ip: Optional[str] = None) -> dict:
        now = time.time()
        window_start = now - self.failed_auth_window_seconds

        if ip:
            attempts = len(
                [t for t in self._failed_auth_attempts.get(ip, []) if t > window_start]
            )
            return {
                "ip": ip,
                "attempts": attempts,
                "max_attempts": self.max_failed_auth_attempts,
                "blocked": self.is_blocked(ip),
            }

        return {
            "ips_with_failures": {
                ip: len([t for t in times if t > window_start])
                for ip, times in self._failed_auth_attempts.items()
                if any(t > window_start for t in times)
            },
            "max_attempts": self.max_failed_auth_attempts,
        }

    def check_rate_limit(self, ip: str) -> tuple[bool, Optional[str]]:
        if self.is_blocked(ip):
            return False, "IP is blocked"

        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        self._minute_requests[ip] = [
            t for t in self._minute_requests[ip] if t > minute_ago
        ]
        self._hour_requests[ip] = [t for t in self._hour_requests[ip] if t > hour_ago]

        if len(self._minute_requests[ip]) >= self.requests_per_minute:
            self.block_ip(ip, "minute_limit")
            return (
                False,
                f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
            )

        if len(self._hour_requests[ip]) >= self.requests_per_hour:
            self.block_ip(ip, "hourly_limit")
            return (
                False,
                f"Rate limit exceeded: {self.requests_per_hour} requests per hour",
            )

        self._minute_requests[ip].append(now)
        self._hour_requests[ip].append(now)

        self._request_count += 1
        if self._request_count % self.CLEANUP_INTERVAL == 0:
            self._cleanup_old_ips(now)

        return True, None

    def _cleanup_old_ips(self, now: float) -> None:
        cutoff = now - (self.CLEANUP_CUTOFF_HOURS * 3600)
        cleaned = 0

        for ip in list(self._minute_requests.keys()):
            if not any(t > cutoff for t in self._minute_requests[ip]):
                del self._minute_requests[ip]
                cleaned += 1

        for ip in list(self._hour_requests.keys()):
            if not any(t > cutoff for t in self._hour_requests[ip]):
                if ip not in self._minute_requests:
                    del self._hour_requests[ip]

        if cleaned > 0:
            logger.debug(f"Rate limiter cleanup: removed {cleaned} inactive IPs")

    def get_stats(self, ip: Optional[str] = None) -> dict:
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        if ip:
            minute_count = len(
                [t for t in self._minute_requests.get(ip, []) if t > minute_ago]
            )
            hour_count = len(
                [t for t in self._hour_requests.get(ip, []) if t > hour_ago]
            )
            return {
                "ip": ip,
                "requests_last_minute": minute_count,
                "requests_last_hour": hour_count,
                "blocked": self.is_blocked(ip),
                "minute_limit": self.requests_per_minute,
                "hour_limit": self.requests_per_hour,
            }

        return {
            "unique_ips_minute": len(
                [
                    ip
                    for ip, times in self._minute_requests.items()
                    if any(t > minute_ago for t in times)
                ]
            ),
            "unique_ips_hour": len(
                [
                    ip
                    for ip, times in self._hour_requests.items()
                    if any(t > hour_ago for t in times)
                ]
            ),
            "blocked_ips_count": len(self.get_blocked_ips()),
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limiter: RateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            request.url.path in ["/health", "/ready"]
            or request.url.path.startswith("/admin/")
            or request.url.path.startswith("/webhooks/")
        ):
            return await call_next(request)

        ip = get_client_ip(request)

        if self.rate_limiter.is_blocked(ip):
            logger.warning(
                "Request from blocked IP", extra={"ip": ip, "path": request.url.path}
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Your IP has been blocked due to rate limit violations. Please try again later."
                },
            )

        allowed, error_message = self.rate_limiter.check_rate_limit(ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": error_message},
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
