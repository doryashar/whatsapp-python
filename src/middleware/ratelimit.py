import time
from collections import defaultdict
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..telemetry import get_logger

logger = get_logger("whatsapp.ratelimit")


class RateLimiter:
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        block_duration_minutes: int = 15,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.block_duration_seconds = block_duration_minutes * 60

        self._minute_requests: dict[str, list[float]] = defaultdict(list)
        self._hour_requests: dict[str, list[float]] = defaultdict(list)
        self._blocked_ips: dict[str, float] = {}

    def is_blocked(self, ip: str) -> bool:
        if ip in self._blocked_ips:
            if time.time() - self._blocked_ips[ip] > self.block_duration_seconds:
                del self._blocked_ips[ip]
                logger.info(f"IP unblocked after cooldown", extra={"ip": ip})
                return False
            return True
        return False

    def block_ip(self, ip: str, reason: str = "rate_limit") -> None:
        self._blocked_ips[ip] = time.time()
        logger.warning(f"IP blocked", extra={"ip": ip, "reason": reason})

    def unblock_ip(self, ip: str) -> bool:
        if ip in self._blocked_ips:
            del self._blocked_ips[ip]
            logger.info(f"IP manually unblocked", extra={"ip": ip})
            return True
        return False

    def get_blocked_ips(self) -> list[dict]:
        now = time.time()
        return [
            {
                "ip": ip,
                "blocked_at": blocked_at,
                "remaining_seconds": max(
                    0, self.block_duration_seconds - (now - blocked_at)
                ),
            }
            for ip, blocked_at in self._blocked_ips.items()
            if now - blocked_at <= self.block_duration_seconds
        ]

    def check_rate_limit(self, ip: str) -> tuple[bool, Optional[str]]:
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        self._minute_requests[ip] = [
            t for t in self._minute_requests[ip] if t > minute_ago
        ]
        self._hour_requests[ip] = [t for t in self._hour_requests[ip] if t > hour_ago]

        if len(self._minute_requests[ip]) >= self.requests_per_minute:
            return (
                False,
                f"Rate limit exceeded: {self.requests_per_minute} requests per minute",
            )

        if len(self._hour_requests[ip]) >= self.requests_per_hour:
            self.block_ip(ip, "hourly_limit_exceeded")
            return (
                False,
                f"Rate limit exceeded: {self.requests_per_hour} requests per hour. IP blocked.",
            )

        self._minute_requests[ip].append(now)
        self._hour_requests[ip].append(now)

        return True, None

    def get_stats(self, ip: Optional[str] = None) -> dict:
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600

        if ip:
            return {
                "ip": ip,
                "blocked": self.is_blocked(ip),
                "requests_last_minute": len(
                    [t for t in self._minute_requests.get(ip, []) if t > minute_ago]
                ),
                "requests_last_hour": len(
                    [t for t in self._hour_requests.get(ip, []) if t > hour_ago]
                ),
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
    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        exclude_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    def get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        if request.url.path.startswith("/admin/"):
            return await call_next(request)

        ip = self.get_client_ip(request)

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
