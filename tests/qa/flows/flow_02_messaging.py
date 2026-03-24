import os
import time
import secrets
import pytest
import requests
from playwright.sync_api import expect

from tests.qa.lib.ui_helper import UIHelper
from tests.qa.lib.tenant_helper import TenantHelper
from tests.qa.lib.message_helper import MessageHelper
from tests.qa.lib.bridge_manager import BridgeManager

pytestmark = [pytest.mark.qa, pytest.mark.flow_02]

QA_BASE_URL = os.environ.get("QA_BASE_URL", "http://localhost:8080")
QA_MESSAGE_TIMEOUT = int(os.environ.get("QA_MESSAGE_TIMEOUT", "60"))


def _get_admin_session() -> requests.Session:
    admin_password = os.environ.get("QA_ADMIN_PASSWORD", "test_admin_password_123")
    s = requests.Session()
    s.post(
        f"{QA_BASE_URL}/admin/login",
        data={"password": admin_password},
        allow_redirects=True,
    )
    return s


def _get_connected_tenants(session: requests.Session) -> list[dict]:
    resp = session.get(f"{QA_BASE_URL}/admin/api/tenants")
    resp.raise_for_status()
    tenants = resp.json().get("tenants", [])
    connected = [
        t
        for t in tenants
        if t.get("connection_state") == "connected" and t.get("self_jid")
    ]
    return connected


@pytest.fixture(scope="class")
def messaging_setup():
    session = _get_admin_session()
    tenants = _get_connected_tenants(session)

    if len(tenants) < 2:
        pytest.skip(
            f"Need at least 2 connected tenants, found {len(tenants)}. "
            "Connect WhatsApp tenants via the admin UI first."
        )

    tenant_a = tenants[0]
    tenant_b = tenants[1]

    if tenant_a.get("self_jid") == tenant_b.get("self_jid"):
        pytest.skip("Tenants must have different JIDs")

    msg_helper = MessageHelper(base_url=QA_BASE_URL, admin_session=session)

    yield {
        "a": tenant_a,
        "b": tenant_b,
        "session": session,
        "msg_helper": msg_helper,
    }

    session.close()


@pytest.fixture(scope="class")
def sent_message(messaging_setup):
    a_hash = messaging_setup["a"]["api_key_hash"]
    b_jid = messaging_setup["b"]["self_jid"]
    msg_helper = messaging_setup["msg_helper"]

    unique_text = f"QA Test {secrets.token_hex(6)} {int(time.time())}"
    result = msg_helper.send_message(
        tenant_hash=a_hash,
        to=b_jid,
        text=unique_text,
    )

    yield {
        "text": unique_text,
        "to": b_jid,
        "result": result,
        "sender_jid": messaging_setup["a"]["self_jid"],
        "a_hash": a_hash,
        "b_hash": messaging_setup["b"]["api_key_hash"],
    }


@pytest.fixture(scope="class")
def tenant_a_sent_msg(messaging_setup, sent_message):
    msg_helper = messaging_setup["msg_helper"]
    a_hash = sent_message["a_hash"]
    text = sent_message["text"]

    msg = msg_helper.wait_for_message(
        tenant_hash=a_hash,
        text=text,
        direction="outbound",
        timeout=QA_MESSAGE_TIMEOUT,
    )

    yield {
        "message": msg,
        "text": text,
        "found": msg is not None,
    }


@pytest.fixture(scope="class")
def tenant_b_received_msg(messaging_setup, sent_message):
    msg_helper = messaging_setup["msg_helper"]
    b_hash = sent_message["b_hash"]
    text = sent_message["text"]
    sender_jid = sent_message["sender_jid"]

    msg = msg_helper.wait_for_message(
        tenant_hash=b_hash,
        text=text,
        timeout=QA_MESSAGE_TIMEOUT,
    )

    yield {
        "message": msg,
        "text": text,
        "sender_jid": sender_jid,
        "found": msg is not None,
    }


@pytest.fixture(scope="class")
def both_messages(tenant_a_sent_msg, tenant_b_received_msg):
    yield {
        "sent": tenant_a_sent_msg["message"],
        "received": tenant_b_received_msg["message"],
        "text": tenant_a_sent_msg["text"],
    }


class TestQATenantsConnected:
    def test_tenant_a_connected(self, messaging_setup):
        a = messaging_setup["a"]
        assert a.get("connection_state") == "connected"
        assert a.get("self_jid")

    def test_tenant_b_connected(self, messaging_setup):
        b = messaging_setup["b"]
        assert b.get("connection_state") == "connected"
        assert b.get("self_jid")

    def test_tenants_have_different_jids(self, messaging_setup):
        a = messaging_setup["a"]
        b = messaging_setup["b"]
        assert a["self_jid"] != b["self_jid"]


class TestQANavigateToTenantAMessages:
    def test_navigate_to_tenant_a_detail(self, qa_ui, messaging_setup):
        ui = qa_ui
        a_hash = messaging_setup["a"]["api_key_hash"]
        ui.navigate(f"/admin/tenants/{a_hash}")
        ui.wait_for_element("nav")
        assert f"/admin/tenants/{a_hash}" in ui.page.url

    def test_messages_tab_visible(self, qa_ui, messaging_setup):
        ui = qa_ui
        a_hash = messaging_setup["a"]["api_key_hash"]
        ui.navigate(f"/admin/tenants/{a_hash}")
        ui.wait_for_element("#tab-content-messages")
        expect(ui.page.locator("#tab-content-messages")).to_be_visible()

    def test_send_form_visible(self, qa_ui, messaging_setup):
        ui = qa_ui
        a_hash = messaging_setup["a"]["api_key_hash"]
        ui.navigate(f"/admin/tenants/{a_hash}")
        ui.wait_for_element("#send-to")
        ui.wait_for_element("#send-text")
        expect(ui.page.locator("#send-to")).to_be_visible()
        expect(ui.page.locator("#send-text")).to_be_visible()

    def test_tenant_name_displayed(self, qa_ui, messaging_setup):
        ui = qa_ui
        a = messaging_setup["a"]
        a_hash = a["api_key_hash"]
        ui.navigate(f"/admin/tenants/{a_hash}")
        ui.page.wait_for_load_state("networkidle")
        expect(ui.page.get_by_text(a["name"])).to_be_visible()


class TestQASendMessageFromAToB:
    def test_send_returns_success(self, sent_message):
        result = sent_message["result"]
        assert result.get("_status_code") == 200, (
            f"Send should return 200, got {result.get('_status_code')}: {result}"
        )
        assert result.get("status") == "sent", f"Status should be sent, got: {result}"

    def test_send_returns_message_id(self, sent_message):
        result = sent_message["result"]
        assert result.get("message_id"), "Response should include a message_id"

    def test_send_returns_recipient_jid(self, sent_message, messaging_setup):
        result = sent_message["result"]
        to = result.get("to", "")
        b_jid = messaging_setup["b"]["self_jid"]
        assert b_jid in to, f"Expected {b_jid} in {to}"


class TestQAMessageAppearsInTenantASent:
    def test_message_found_in_tenant_a(self, tenant_a_sent_msg):
        assert tenant_a_sent_msg["found"], (
            f"Message not found in tenant A within {QA_MESSAGE_TIMEOUT}s"
        )

    def test_message_is_outbound(self, tenant_a_sent_msg):
        msg = tenant_a_sent_msg["message"]
        assert msg is not None
        assert msg.get("direction") == "outbound"

    def test_message_text_matches(self, tenant_a_sent_msg):
        msg = tenant_a_sent_msg["message"]
        assert msg is not None
        assert tenant_a_sent_msg["text"] in msg.get("text", "")


class TestQAMessageReceivedInTenantB:
    def test_message_found_in_tenant_b(self, tenant_b_received_msg):
        assert tenant_b_received_msg["found"], (
            f"Message not received in tenant B within {QA_MESSAGE_TIMEOUT}s"
        )

    def test_message_is_inbound(self, tenant_b_received_msg):
        msg = tenant_b_received_msg["message"]
        assert msg is not None
        assert msg.get("direction") == "inbound"

    def test_received_text_matches_sent(self, tenant_b_received_msg):
        msg = tenant_b_received_msg["message"]
        assert msg is not None
        expected = tenant_b_received_msg["text"]
        assert expected in msg.get("text", "")

    def test_sender_matches_tenant_a(self, tenant_b_received_msg, messaging_setup):
        msg = tenant_b_received_msg["message"]
        if msg is None:
            pytest.skip("Message not found in tenant B")
        sender_jid = messaging_setup["a"]["self_jid"]
        from_jid = msg.get("from_jid", msg.get("from", ""))
        assert sender_jid in from_jid, (
            f"Sender mismatch: expected {sender_jid} in {from_jid}"
        )


class TestQAMessageDetailsMatch:
    def test_same_text_in_both_tenants(self, both_messages):
        sent = both_messages["sent"]
        received = both_messages["received"]
        if sent is None or received is None:
            pytest.skip("One or both messages not found")
        assert sent.get("text") == received.get("text")

    def test_opposite_directions(self, both_messages):
        sent = both_messages["sent"]
        received = both_messages["received"]
        if sent is None or received is None:
            pytest.skip("One or both messages not found")
        assert sent.get("direction") == "outbound"
        assert received.get("direction") == "inbound"

    def test_message_appears_via_ui_in_tenant_b(
        self, qa_ui, messaging_setup, sent_message
    ):
        ui = qa_ui
        b_hash = messaging_setup["b"]["api_key_hash"]
        text = sent_message["text"]

        ui.navigate(f"/admin/tenants/{b_hash}")
        ui.switch_tab("Messages")
        ui.page.wait_for_timeout(2000)

        message_area = ui.page.locator("#tenant-messages")
        try:
            expect(message_area.get_by_text(text)).to_be_visible(timeout=15000)
        except Exception:
            ui.page.locator("#tenant-messages").click()
            ui.page.wait_for_timeout(1000)
            try:
                expect(message_area.get_by_text(text)).to_be_visible(timeout=10000)
            except Exception:
                ui.screenshot("tenant_b_message_not_found")
                pytest.fail(f"Message not visible in tenant B UI")

    def test_message_visible_via_ui_in_tenant_a(
        self, qa_ui, messaging_setup, sent_message
    ):
        ui = qa_ui
        a_hash = messaging_setup["a"]["api_key_hash"]
        text = sent_message["text"]

        ui.navigate(f"/admin/tenants/{a_hash}")
        ui.switch_tab("Messages")
        ui.page.wait_for_timeout(2000)

        message_area = ui.page.locator("#tenant-messages")
        try:
            expect(message_area.get_by_text(text)).to_be_visible(timeout=15000)
        except Exception:
            ui.screenshot("tenant_a_message_not_found")
            pytest.fail(f"Message not visible in tenant A UI")
