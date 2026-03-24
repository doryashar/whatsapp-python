import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, UTC


ADMIN_PASSWORD = "test-admin-password-123"


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


@pytest.fixture
async def db(tmp_path):
    from src.store.database import Database

    database = Database("", tmp_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def setup_tenant_manager(db, monkeypatch):
    from src.tenant import tenant_manager

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()

    tenant_manager.set_database(db)
    tenant_manager._tenants.clear()

    yield tenant_manager

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants


@pytest.fixture(autouse=True)
def setup_admin_password(monkeypatch):
    from src import config

    monkeypatch.setattr(config.settings, "admin_password", ADMIN_PASSWORD)
    monkeypatch.setattr(config.settings, "debug", True)
    yield
    monkeypatch.setattr(config.settings, "admin_password", None)
    monkeypatch.setattr(config.settings, "debug", False)


@pytest.fixture
async def with_tenant(setup_tenant_manager):
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")
    yield tenant, api_key
    await tenant_manager.delete_tenant(api_key)


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring live services")
