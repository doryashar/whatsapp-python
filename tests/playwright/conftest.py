import os
import hashlib
import secrets
from typing import Generator
from unittest.mock import patch
from datetime import datetime

import pytest
from playwright.sync_api import Page, Browser, BrowserContext

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.tenant import tenant_manager, Tenant
from src.store.database import Database
from src.store.messages import MessageStore, StoredMessage
from src.middleware import rate_limiter


ADMIN_PASSWORD = "test_admin_password_123"
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")


def get_event_loop():
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@pytest.fixture
def db_session():
    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()

    db = Database(":memory:")
    loop = get_event_loop()
    loop.run_until_complete(db.init())
    yield db

    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()


@pytest.fixture
def test_tenant(db_session: Database):
    raw_key = f"wa_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    tenant = Tenant(
        api_key_hash=key_hash,
        name="test_tenant_playwright",
        message_store=MessageStore(
            max_messages=1000,
            tenant_hash=key_hash,
            db=db_session,
        ),
    )

    tenant.connection_state = "connected"
    tenant._jid = "1234567890@s.whatsapp.net"

    tenant_manager._tenants[key_hash] = tenant

    loop = get_event_loop()
    loop.run_until_complete(
        db_session.save_tenant(
            tenant.api_key_hash,
            tenant.name,
            tenant.created_at,
            tenant.webhook_urls,
        )
    )

    yield {"tenant": tenant, "api_key": raw_key, "hash": key_hash}

    if key_hash in tenant_manager._tenants:
        del tenant_manager._tenants[key_hash]


@pytest.fixture
def multiple_tenants(db_session: Database):
    tenants = []
    loop = get_event_loop()

    for i in range(3):
        raw_key = f"wa_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        tenant = Tenant(
            api_key_hash=key_hash,
            name=f"test_tenant_{i}",
            message_store=MessageStore(
                max_messages=1000,
                tenant_hash=key_hash,
                db=db_session,
            ),
        )
        tenant.connection_state = "connected" if i % 2 == 0 else "pending_qr"

        tenant_manager._tenants[key_hash] = tenant
        loop.run_until_complete(
            db_session.save_tenant(
                tenant.api_key_hash,
                tenant.name,
                tenant.created_at,
                tenant.webhook_urls,
            )
        )

        tenants.append({"tenant": tenant, "api_key": raw_key, "hash": key_hash})

    yield tenants

    for t in tenants:
        if t["hash"] in tenant_manager._tenants:
            del tenant_manager._tenants[t["hash"]]


@pytest.fixture
def test_messages(db_session: Database, test_tenant: dict):
    messages = []
    tenant_hash = test_tenant["hash"]
    loop = get_event_loop()

    for i in range(5):
        msg = StoredMessage(
            id=f"msg_{i}_{secrets.token_hex(8)}",
            from_jid=f"123456789{i}@s.whatsapp.net",
            chat_jid=f"123456789{i}@s.whatsapp.net",
            is_group=False,
            push_name=f"Contact {i}",
            text=f"Test message {i}",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
            direction="inbound" if i % 2 == 0 else "outbound",
        )
        loop.run_until_complete(db_session.save_message(tenant_hash, msg))
        messages.append(msg)

    yield messages

    loop.run_until_complete(db_session.clear_tenant_messages(tenant_hash))


@pytest.fixture
def blocked_ip():
    rate_limiter.block_ip("192.168.1.100", "failed_auth")
    yield "192.168.1.100"
    rate_limiter.unblock_ip("192.168.1.100")


@pytest.fixture
def webhook_test_tenant(test_tenant: dict):
    test_tenant["tenant"].webhook_urls = [
        "https://webhook1.example.com/hook",
        "https://webhook2.example.com/hook",
    ]
    yield test_tenant


def create_admin_session_sync(db: Database) -> str:
    session_id = secrets.token_urlsafe(32)
    loop = get_event_loop()
    loop.run_until_complete(
        db.execute(
            """INSERT INTO admin_sessions (session_id, created_at, expires_at, ip_address, user_agent)
               VALUES ($1, NOW(), NOW() + INTERVAL '24 hours', '127.0.0.1', 'Playwright')""",
            session_id,
        )
    )
    return session_id


@pytest.fixture
def authenticated_page(page: Page, db_session: Database):
    session_id = create_admin_session_sync(db_session)
    page.context.add_cookies(
        [
            {
                "name": "admin_session",
                "value": session_id,
                "domain": "localhost",
                "path": "/",
            }
        ]
    )
    yield page


class MockRoutes:
    @staticmethod
    def mock_chatwoot_api(route, request):
        route.fulfill(
            status=200, content_type="application/json", body='{"success": true}'
        )

    @staticmethod
    def mock_webhook_delivery(route, request):
        route.fulfill(
            status=200, content_type="application/json", body='{"received": true}'
        )

    @staticmethod
    def mock_bridge_status(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body='{"connection_state": "connected", "jid": "1234567890@s.whatsapp.net"}',
        )


@pytest.fixture
def mock_external_routes(page: Page):
    page.route("**/chatwoot**", MockRoutes.mock_chatwoot_api)
    page.route("**/webhook**", MockRoutes.mock_webhook_delivery)
    page.route("**/bridge**", MockRoutes.mock_bridge_status)
    yield
    page.unroute("**/chatwoot**", MockRoutes.mock_chatwoot_api)
    page.unroute("**/webhook**", MockRoutes.mock_webhook_delivery)
    page.unroute("**/bridge**", MockRoutes.mock_bridge_status)


def pytest_configure(config):
    config.addinivalue_line("markers", "playwright: browser-based UI tests")
    config.addinivalue_line("markers", "slow: tests that take more than 5 seconds")
    config.addinivalue_line("markers", "accessibility: accessibility-related tests")
    config.addinivalue_line("markers", "responsive: responsive design tests")
    config.addinivalue_line("markers", "websocket: WebSocket-related tests")
