import pytest
import asyncio


def requires_pg(test_func):
    """Decorator to skip test if testcontainers-postgres is not available."""
    try:
        import testcontainers.postgres

        return test_func
    except ImportError:
        return pytest.mark.skip("testcontainers-postgres not installed")(test_func)


@pytest.fixture(scope="session")
def pg_container():
    """Spin up a PostgreSQL container for the test session."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers-postgres not installed")
        return None, None

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container):
    """Get the PostgreSQL connection URL from the container."""
    if pg_container is None:
        return None
    return pg_container.get_connection_url()


@pytest.fixture
async def pg_db(pg_url, tmp_path):
    """Create a Database instance connected to PostgreSQL."""
    if pg_url is None:
        pytest.skip("PostgreSQL container not available")
        return None

    from src.store.database import Database

    database = Database(pg_url, tmp_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def pg_tenant_manager(pg_db, monkeypatch):
    """Set up tenant_manager with PostgreSQL backend."""
    if pg_db is None:
        return None

    from src.tenant import tenant_manager

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()

    tenant_manager.set_database(pg_db)
    tenant_manager._tenants.clear()

    yield tenant_manager

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants
