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


def test_failed_auth_auto_block():
    limiter = RateLimiter(
        max_failed_auth_attempts=3,
        failed_auth_window_minutes=15,
        block_duration_minutes=30,
    )

    assert not limiter.is_blocked("10.0.0.1")

    attempts, blocked = limiter.record_failed_auth("10.0.0.1")
    assert attempts == 1
    assert not blocked

    attempts, blocked = limiter.record_failed_auth("10.0.0.1")
    assert attempts == 2
    assert not blocked

    attempts, blocked = limiter.record_failed_auth("10.0.0.1")
    assert attempts == 3
    assert blocked

    assert limiter.is_blocked("10.0.0.1")

    blocked_ips = limiter.get_blocked_ips()
    assert len(blocked_ips) == 1
    assert blocked_ips[0]["ip"] == "10.0.0.1"
    assert "failed_auth" in blocked_ips[0]["reason"]


def test_clear_failed_auth():
    limiter = RateLimiter(max_failed_auth_attempts=5)

    limiter.record_failed_auth("192.168.1.1")
    limiter.record_failed_auth("192.168.1.1")

    stats = limiter.get_failed_auth_attempts("192.168.1.1")
    assert stats["attempts"] == 2

    limiter.clear_failed_auth("192.168.1.1")

    stats = limiter.get_failed_auth_attempts("192.168.1.1")
    assert stats["attempts"] == 0


def test_failed_auth_multiple_ips():
    limiter = RateLimiter(max_failed_auth_attempts=5)

    limiter.record_failed_auth("10.0.0.1")
    limiter.record_failed_auth("10.0.0.2")
    limiter.record_failed_auth("10.0.0.1")

    all_stats = limiter.get_failed_auth_attempts()
    assert "10.0.0.1" in all_stats["ips_with_failures"]
    assert "10.0.0.2" in all_stats["ips_with_failures"]
    assert all_stats["ips_with_failures"]["10.0.0.1"] == 2
    assert all_stats["ips_with_failures"]["10.0.0.2"] == 1


def test_unblock_clears_failed_auth():
    limiter = RateLimiter(max_failed_auth_attempts=3)

    for _ in range(3):
        limiter.record_failed_auth("10.0.0.5")

    assert limiter.is_blocked("10.0.0.5")
    assert limiter.get_failed_auth_attempts("10.0.0.5")["attempts"] == 3

    limiter.unblock_ip("10.0.0.5")

    assert not limiter.is_blocked("10.0.0.5")
    assert limiter.get_failed_auth_attempts("10.0.0.5")["attempts"] == 0


class TestIPCleanup:
    def test_cleanup_removes_stale_ips_from_minute_window(self):
        import time
        from collections import deque

        limiter = RateLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
            block_duration_minutes=60,
        )

        limiter.check_rate_limit("10.0.0.1")
        assert "10.0.0.1" in limiter._minute_requests

        old_time = time.time() - 7200
        limiter._minute_requests["10.0.0.1"] = deque([old_time])

        limiter._cleanup_old_ips(time.time())

        assert len(limiter._minute_requests.get("10.0.0.1", [])) == 0

    def test_cleanup_removes_stale_ips_from_hour_window(self):
        import time
        from collections import deque

        limiter = RateLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
            block_duration_minutes=60,
        )

        limiter.check_rate_limit("10.0.0.2")
        assert "10.0.0.2" in limiter._hour_requests

        old_time = time.time() - 7200
        limiter._hour_requests["10.0.0.2"] = deque([old_time])

        limiter._cleanup_old_ips(time.time())

        assert len(limiter._hour_requests.get("10.0.0.2", [])) == 0

    def test_cleanup_preserves_active_ips(self):
        import time
        from collections import deque

        limiter = RateLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
        )

        recent_time = time.time() - 60
        limiter._minute_requests["10.0.0.3"] = deque([recent_time])
        limiter._hour_requests["10.0.0.3"] = deque([recent_time])

        limiter._cleanup_old_ips(time.time())

        assert "10.0.0.3" in limiter._minute_requests
        assert "10.0.0.3" in limiter._hour_requests

    def test_cleanup_does_not_remove_blocked_ips(self):
        import time
        from collections import deque

        limiter = RateLimiter()
        limiter.block_ip("10.0.0.4", reason="test")

        limiter._minute_requests["10.0.0.4"] = deque([time.time() - 7200])
        limiter._hour_requests["10.0.0.4"] = deque([time.time() - 7200])

        limiter._cleanup_old_ips(time.time())

        assert limiter.is_blocked("10.0.0.4")

    def test_cleanup_triggered_periodically(self):
        import time

        limiter = RateLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
        )

        limiter.check_rate_limit("10.0.0.5")
        limiter.check_rate_limit("10.0.0.6")
        limiter.check_rate_limit("10.0.0.7")

        assert limiter._request_count == 3

        original_cleanup = limiter._cleanup_old_ips
        cleanup_called = []

        def spy_cleanup(now):
            cleanup_called.append(True)
            original_cleanup(now)

        limiter._cleanup_old_ips = spy_cleanup

        for _ in range(100):
            limiter.check_rate_limit("10.0.0.8")

        assert len(cleanup_called) >= 1

    def test_stats_reflect_cleanup(self):
        import time
        from collections import deque

        limiter = RateLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
        )

        limiter.check_rate_limit("10.0.0.9")
        limiter.check_rate_limit("10.0.0.10")

        stats_before = limiter.get_stats()
        assert stats_before["unique_ips_minute"] >= 2

        limiter._minute_requests["10.0.0.9"] = deque([time.time() - 7200])
        limiter._minute_requests["10.0.0.10"] = deque([time.time() - 7200])

        limiter._cleanup_old_ips(time.time())

        stats_after = limiter.get_stats()
        assert stats_after["unique_ips_minute"] == 0
