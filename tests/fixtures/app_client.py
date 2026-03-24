import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from src.tenant import Tenant


@pytest.fixture
def app_client(db, monkeypatch):
    """Create a TestClient with mocked dependencies."""
    from src.main import app
    from src.tenant import tenant_manager

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()
    original_event_handler = tenant_manager._event_handler

    tenant_manager.set_database(db)
    tenant_manager._tenants.clear()

    client = TestClient(app, raise_server_exceptions=False)

    yield client, tenant_manager

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants
    tenant_manager._event_handler = original_event_handler


@pytest.fixture
def app_client_with_tenant(app_client, setup_tenant_manager):
    """Create a TestClient with a pre-created tenant."""
    client, tm = app_client
    tenant, api_key = None, None

    import asyncio

    loop = asyncio.get_event_loop()
    tenant, api_key = loop.run_until_complete(tm.create_tenant("Test Tenant"))

    yield client, tenant, api_key

    if tenant and api_key:
        loop.run_until_complete(tm.delete_tenant(api_key))


@pytest.fixture
def admin_client(db, monkeypatch):
    """Create a TestClient with admin authentication."""
    from src.main import app
    from src.tenant import tenant_manager
    from src.config import settings

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()

    tenant_manager.set_database(db)
    tenant_manager._tenants.clear()

    monkeypatch.setattr(settings, "admin_api_key", "test-admin-key")

    client = TestClient(app, raise_server_exceptions=False)

    yield client

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants
