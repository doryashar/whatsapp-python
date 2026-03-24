import os
import hashlib
import secrets
import tempfile
import requests
from pathlib import Path
from typing import Generator
from unittest.mock import patch
from datetime import datetime, timezone

import pytest
from playwright.sync_api import Page, Browser, BrowserContext

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import nest_asyncio

nest_asyncio.apply()

import asyncio
from src.tenant import tenant_manager, Tenant
from src.store.database import Database
from src.store.messages import MessageStore, StoredMessage
from src.middleware import rate_limiter


def _load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.normpath(env_path)
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


_load_env_file()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "test_admin_password_123")
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")


def get_event_loop():
    try:
        loop = asyncio.get_running_loop()
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _get_database_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


def _is_postgres():
    return _get_database_url().startswith(("postgresql://", "postgres://"))


class _SyncDB:
    def __init__(self, url):
        import psycopg2

        self._conn = psycopg2.connect(url)

    def save_message(
        self,
        *,
        tenant_hash,
        message_id,
        from_jid,
        chat_jid,
        is_group=False,
        push_name=None,
        text="",
        msg_type="text",
        timestamp=0,
        direction="inbound",
        media_url=None,
        mimetype=None,
        filename=None,
        latitude=None,
        longitude=None,
        location_name=None,
        location_address=None,
        chat_name=None,
    ):
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (tenant_hash, message_id, from_jid, chat_jid,
                    is_group, push_name, text, msg_type, timestamp, direction,
                    media_url, mimetype, filename, latitude, longitude,
                    location_name, location_address)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_hash, message_id) DO NOTHING
                RETURNING id
            """,
                (
                    tenant_hash,
                    message_id,
                    from_jid,
                    chat_jid,
                    is_group,
                    push_name,
                    text,
                    msg_type,
                    timestamp,
                    direction,
                    media_url,
                    mimetype,
                    filename,
                    latitude,
                    longitude,
                    location_name,
                    location_address,
                ),
            )
            result = cur.fetchone()
            self._conn.commit()
            if result:
                phone = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
                contact_name = chat_name if chat_name else push_name
                self.upsert_contact(
                    tenant_hash, phone, contact_name, chat_jid, is_group
                )
            return result[0] if result else None

    def upsert_contact(
        self, tenant_hash, phone, name, chat_jid, is_group=False, message_time=None
    ):
        if message_time is None:
            message_time = datetime.now(timezone.utc)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contacts (tenant_hash, phone, name, chat_jid, is_group,
                    last_message_at, message_count, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,1,NOW(),NOW())
                ON CONFLICT (tenant_hash, phone) DO UPDATE SET
                    name = CASE WHEN EXCLUDED.name IS NOT NULL AND EXCLUDED.name != ''
                        THEN EXCLUDED.name ELSE contacts.name END,
                    chat_jid = EXCLUDED.chat_jid,
                    is_group = EXCLUDED.is_group,
                    last_message_at = EXCLUDED.last_message_at,
                    message_count = contacts.message_count + 1,
                    updated_at = NOW()
            """,
                (tenant_hash, phone, name, chat_jid, is_group, message_time),
            )
            self._conn.commit()

    def delete_tenant_messages(self, tenant_hash):
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM messages WHERE tenant_hash = %s", (tenant_hash,))
            msg_count = cur.rowcount
            cur.execute("DELETE FROM contacts WHERE tenant_hash = %s", (tenant_hash,))
            contact_count = cur.rowcount
            self._conn.commit()
        return {"messages": msg_count, "contacts": contact_count}

    def close(self):
        self._conn.close()


def _seed_db():
    url = _get_database_url()
    if url.startswith(("postgresql://", "postgres://")):
        try:
            db = _SyncDB(url)
            with db._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return db
        except Exception:
            pass
    return None


def _admin_session():
    import re

    s = requests.Session()
    admin_password = os.environ.get("ADMIN_PASSWORD", ADMIN_PASSWORD)
    resp = s.post(
        f"{BASE_URL}/admin/login",
        data={"password": admin_password},
        allow_redirects=False,
    )
    m = re.search(r"admin_session=([^;]+)", resp.headers.get("set-cookie", ""))
    if m:
        s.cookies.clear()
        s.cookies.set("admin_session", m.group(1))
    return s


def _create_tenant_via_api(session, name):
    resp = session.post(f"{BASE_URL}/admin/api/tenants", data={"name": name})
    resp.raise_for_status()
    data = resp.json()
    return data["tenant"]


def _delete_tenant_via_api(session, tenant_hash):
    session.delete(f"{BASE_URL}/admin/api/tenants/{tenant_hash}")


@pytest.fixture
def db_session():
    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()

    database_url = _get_database_url()
    if database_url.startswith(("postgresql://", "postgres://")):
        db = _SyncDB(database_url)
    else:
        shared_data_dir = os.environ.get("PW_SHARED_DATA_DIR", "")
        if shared_data_dir:
            tmp_dir = shared_data_dir
        else:
            tmp_dir = tempfile.mkdtemp()
        db = Database("sqlite:///:memory:", Path(tmp_dir))
        loop = get_event_loop()
        loop.run_until_complete(db.connect())
    yield db

    if isinstance(db, _SyncDB):
        db.close()
    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    rate_limiter._minute_requests.clear()
    rate_limiter._hour_requests.clear()


@pytest.fixture
def test_tenant():
    session = _admin_session()
    tenant_name = f"pw_test_tenant_{secrets.token_hex(4)}"
    tenant_data = _create_tenant_via_api(session, tenant_name)
    print(
        f"[FIXTURE] test_tenant created: {tenant_name}, hash={tenant_data['api_key_hash'][:20]}"
    )
    tenant_hash = tenant_data["api_key_hash"]
    raw_key = tenant_data.get("api_key", "")

    yield {
        "tenant": tenant_data,
        "api_key": raw_key,
        "hash": tenant_hash,
        "name": tenant_name,
    }

    _delete_tenant_via_api(session, tenant_hash)
    session.close()


@pytest.fixture
def multiple_tenants():
    session = _admin_session()
    tenants = []

    for i in range(3):
        tenant_name = f"pw_test_tenant_{i}_{secrets.token_hex(4)}"
        tenant_data = _create_tenant_via_api(session, tenant_name)
        tenant_hash = tenant_data["api_key_hash"]
        raw_key = tenant_data.get("api_key", "")
        tenants.append(
            {
                "tenant": tenant_data,
                "api_key": raw_key,
                "hash": tenant_hash,
                "name": tenant_name,
            }
        )

    yield tenants

    for t in tenants:
        _delete_tenant_via_api(session, t["hash"])
    session.close()


@pytest.fixture
def test_messages(test_tenant):
    db = _seed_db()
    tenant_hash = test_tenant["hash"]
    messages = []

    if db is None:
        yield []
        return

    for i in range(5):
        msg_id = f"msg_{i}_{secrets.token_hex(8)}"
        db.save_message(
            tenant_hash=tenant_hash,
            message_id=msg_id,
            from_jid=f"123456789{i}@s.whatsapp.net",
            chat_jid=f"123456789{i}@s.whatsapp.net",
            is_group=False,
            push_name=f"Contact {i}",
            text=f"Test message {i}",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000) - (i * 60000),
            direction="inbound" if i % 2 == 0 else "outbound",
        )
        messages.append({"id": msg_id, "from": f"123456789{i}@s.whatsapp.net"})

    yield messages

    db.delete_tenant_messages(tenant_hash)
    db.close()


@pytest.fixture
def blocked_ip():
    rate_limiter.block_ip("192.168.1.100", "failed_auth")
    yield "192.168.1.100"
    rate_limiter.unblock_ip("192.168.1.100")


@pytest.fixture
def webhook_test_tenant(test_tenant):
    session = _admin_session()
    tenant_hash = test_tenant["hash"]
    try:
        session.post(
            f"{BASE_URL}/admin/api/tenants/{tenant_hash}/webhooks",
            json={"url": "https://httpbin.org/post"},
        )
        session.post(
            f"{BASE_URL}/admin/api/tenants/{tenant_hash}/webhooks",
            json={"url": "https://httpbin.org/webhook"},
        )
    except Exception:
        pass
    yield test_tenant
    session.close()


def create_admin_session_sync(db: Database) -> str:
    session_id = secrets.token_urlsafe(32)
    loop = get_event_loop()
    from datetime import timedelta

    expires_at = datetime.now() + timedelta(hours=24)
    loop.run_until_complete(
        db.create_admin_session(
            session_id=session_id,
            expires_at=expires_at,
            user_agent="Playwright",
            ip_address="127.0.0.1",
        )
    )
    return session_id


@pytest.fixture(scope="session")
def admin_browser_context(browser: Browser):
    context = browser.new_context()
    page = context.new_page()
    admin_password = os.environ.get("ADMIN_PASSWORD", ADMIN_PASSWORD)
    page.goto(f"{BASE_URL}/admin/login")
    page.wait_for_selector('input[name="password"]', timeout=15000)
    page.fill('input[name="password"]', admin_password)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=15000)
    page.close()
    yield context
    context.close()


@pytest.fixture
def authenticated_page(admin_browser_context: BrowserContext):
    page = admin_browser_context.new_page()
    page.set_default_timeout(10000)
    page.set_default_navigation_timeout(15000)
    yield page
    page.close()


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
