from .ratelimit import RateLimiter, RateLimitMiddleware
from ..config import settings

rate_limiter = RateLimiter(
    requests_per_minute=settings.rate_limit_per_minute,
    requests_per_hour=settings.rate_limit_per_hour,
    block_duration_minutes=settings.rate_limit_block_minutes,
)

__all__ = ["RateLimiter", "RateLimitMiddleware", "rate_limiter"]
