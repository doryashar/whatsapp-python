import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.ratelimit import RateLimiter, RateLimitMiddleware


def rate_limit_app():
    app = FastAPI()
    limiter = RateLimiter(
        requests_per_minute=5,
        requests_per_hour=10,
        block_duration_minutes=1,
    )
    app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app, limiter


def test_rate_limit_allows_requests():
    app, _ = rate_limit_app()
    client = TestClient(app)

    for _ in range(3):
        response = client.get("/test")
        assert response.status_code == 200


def test_rate_limit_excludes_health():
    app, _ = rate_limit_app()
    client = TestClient(app, raise_server_exceptions=False)

    for _ in range(10):
        response = client.get("/health")
        assert response.status_code == 200


def test_rate_limit_blocks_after_minute_limit():
    limiter = RateLimiter(
        requests_per_minute=3, requests_per_hour=100, block_duration_minutes=1
    )
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)

    for _ in range(3):
        response = client.get("/test")
        assert response.status_code == 200

    response = client.get("/test")
    assert response.status_code == 429


def test_manual_ip_block():
    limiter = RateLimiter()

    assert not limiter.is_blocked("192.168.1.1")

    limiter.block_ip("192.168.1.1", reason="test")
    assert limiter.is_blocked("192.168.1.1")


def test_manual_ip_unblock():
    limiter = RateLimiter()

    limiter.block_ip("192.168.1.2", reason="test")
    assert limiter.is_blocked("192.168.1.2")

    result = limiter.unblock_ip("192.168.1.2")
    assert result is True
    assert not limiter.is_blocked("192.168.1.2")


def test_get_blocked_ips():
    limiter = RateLimiter(block_duration_minutes=60)

    assert len(limiter.get_blocked_ips()) == 0

    limiter.block_ip("10.0.0.1", reason="test1")
    limiter.block_ip("10.0.0.2", reason="test2")

    blocked = limiter.get_blocked_ips()
    assert len(blocked) == 2
    ips = [b["ip"] for b in blocked]
    assert "10.0.0.1" in ips
    assert "10.0.0.2" in ips


def test_rate_limit_stats():
    limiter = RateLimiter()

    stats = limiter.get_stats()
    assert "unique_ips_minute" in stats
    assert "unique_ips_hour" in stats
    assert "blocked_ips_count" in stats

    limiter.check_rate_limit("192.168.1.1")
    limiter.check_rate_limit("192.168.1.1")
    limiter.check_rate_limit("192.168.1.2")

    ip_stats = limiter.get_stats("192.168.1.1")
    assert ip_stats["ip"] == "192.168.1.1"
    assert ip_stats["requests_last_minute"] == 2
