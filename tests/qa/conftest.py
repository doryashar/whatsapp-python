import os
import secrets
import requests

import pytest
from playwright.sync_api import Page, Browser, BrowserContext

from tests.qa.lib.ui_helper import UIHelper, BASE_URL, SCREENSHOT_DIR
from tests.qa.lib.tenant_helper import TenantHelper
from tests.qa.lib.message_helper import MessageHelper
from tests.qa.lib.bridge_manager import BridgeManager


QA_ADMIN_PASSWORD = os.environ.get("QA_ADMIN_PASSWORD", "test_admin_password_123")


def pytest_configure(config):
    config.addinivalue_line("markers", "qa: QA engineer flow tests")
    config.addinivalue_line("markers", "flow_01: Sign-in flow")
    config.addinivalue_line("markers", "flow_02: Messaging flow (send + verify)")
    config.addinivalue_line("markers", "flow_03: Message lifecycle flow")
    config.addinivalue_line("markers", "flow_04: Full UI coverage flow")


def _admin_session() -> requests.Session:
    s = requests.Session()
    s.post(
        f"{BASE_URL}/admin/login",
        data={"password": QA_ADMIN_PASSWORD},
        allow_redirects=True,
    )
    return s


@pytest.fixture(scope="session")
def qa_base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def qa_admin_password():
    return QA_ADMIN_PASSWORD


@pytest.fixture(scope="session")
def qa_browser_context(browser: Browser, qa_admin_password: str):
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{BASE_URL}/admin/login")
    page.wait_for_selector('input[name="password"]', timeout=15000)
    page.fill('input[name="password"]', qa_admin_password)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=15000)
    page.close()
    yield context
    context.close()


@pytest.fixture
def qa_page(qa_browser_context: BrowserContext):
    page = qa_browser_context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)
    yield page
    page.close()


@pytest.fixture
def qa_ui(qa_page: Page):
    return UIHelper(qa_page)


@pytest.fixture(scope="session")
def qa_http_session():
    session = _admin_session()
    yield session
    session.close()


@pytest.fixture
def qa_tenant_helper(qa_http_session: requests.Session):
    helper = TenantHelper(base_url=BASE_URL)
    helper.session = qa_http_session
    yield helper


@pytest.fixture
def qa_message_helper(qa_http_session: requests.Session):
    return MessageHelper(base_url=BASE_URL, admin_session=qa_http_session)


@pytest.fixture
def qa_bridge(qa_http_session: requests.Session):
    return BridgeManager(base_url=BASE_URL, admin_session=qa_http_session)


@pytest.fixture
def qa_unauth_page(browser: Browser):
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)
    yield page
    page.close()
    context.close()


@pytest.fixture
def qa_unauth_ui(qa_unauth_page: Page):
    return UIHelper(qa_unauth_page)


@pytest.fixture
def qa_tenant_a(qa_tenant_helper: TenantHelper):
    name = f"QA_Tenant_A_{secrets.token_hex(4)}"
    tenant = qa_tenant_helper.create_tenant(name)
    yield tenant
    try:
        qa_tenant_helper.delete_tenant(tenant["hash"])
    except Exception:
        pass


@pytest.fixture
def qa_tenant_b(qa_tenant_helper: TenantHelper):
    name = f"QA_Tenant_B_{secrets.token_hex(4)}"
    tenant = qa_tenant_helper.create_tenant(name)
    yield tenant
    try:
        qa_tenant_helper.delete_tenant(tenant["hash"])
    except Exception:
        pass
