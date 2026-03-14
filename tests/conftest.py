import pytest
import asyncio


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from src.middleware import rate_limiter

    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()
    yield
    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live services")
