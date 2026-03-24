import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import ADMIN_PASSWORD


TENANT_HASH = "th_test_messages_ui"


def _make_message(**overrides):
    defaults = {
        "id": 1,
        "tenant_hash": TENANT_HASH,
        "message_id": "msg_1",
        "from_jid": "1111111111@s.whatsapp.net",
        "chat_jid": "1111111111@s.whatsapp.net",
        "is_group": False,
        "push_name": "Test User",
        "text": "Hello world",
        "msg_type": "text",
        "timestamp": 1700000000,
        "direction": "inbound",
        "created_at": "2024-01-01 12:00:00",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
async def with_tenant(setup_tenant_manager):
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("MsgUI Test")
    yield tenant, api_key
    await tenant_manager.delete_tenant(api_key)


class TestMessageDisplayFormat:
    @pytest.mark.asyncio
    async def test_private_message_shows_private_label(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash, is_group=False, push_name="Alice"
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            assert resp.status_code == 200
            html = resp.text
            assert "Alice" in html
            assert "From: Alice" in html
            assert "Chat: private" in html
            assert "text-orange-400" not in html

    @pytest.mark.asyncio
    async def test_group_message_shows_group_name(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                is_group=True,
                push_name="Bob",
                chat_jid="family@g.us",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={
                (tenant.api_key_hash, "family@g.us"): {
                    "name": "Family Group",
                    "is_group": True,
                }
            }
        )
        setup_tenant_manager._db.get_contact_names_for_senders = AsyncMock(
            return_value={}
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "Bob" in html
            assert "From: Bob" in html
            assert "Family Group" in html
            assert "Chat: Family Group" in html
            assert "text-orange-400" in html

    @pytest.mark.asyncio
    async def test_group_message_fallback_without_contact(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                is_group=True,
                push_name="Bob",
                chat_jid="unknown@g.us",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={}
        )
        setup_tenant_manager._db.get_contact_names_for_senders = AsyncMock(
            return_value={}
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "Chat: group" in html

    @pytest.mark.asyncio
    async def test_uses_sender_contact_name_when_no_push_name(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                push_name="",
                from_jid="555123@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_senders = AsyncMock(
            return_value={
                (tenant.api_key_hash, "555123@s.whatsapp.net"): {
                    "name": "Dave Smith",
                    "is_group": False,
                }
            }
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "From: Dave Smith" in html
            assert "555123" not in html

    @pytest.mark.asyncio
    async def test_uses_push_name_over_contact_name(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                push_name="Charlie",
                from_jid="999@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "Charlie" in html
            assert "999@s.whatsapp.net" not in html

    @pytest.mark.asyncio
    async def test_falls_back_to_jid_without_push_name(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                push_name="",
                from_jid="999123@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "999123" in html

    @pytest.mark.asyncio
    async def test_reply_button_with_data_attributes(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [_make_message(tenant_hash=tenant.api_key_hash, message_id="msg_abc")]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "openReplyModal" in html
            assert 'data-message-id="msg_abc"' in html
            assert "data-tenant-hash=" in html
            assert "data-chat-jid=" in html
            assert "data-from-name=" in html
            assert "data-quoted-text=" in html

    @pytest.mark.asyncio
    async def test_reply_button_html_escaping(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                push_name="O'Brian <script>",
                text="Hello 'world'",
                message_id="msg_escape",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "&#39;" in html
            assert "&lt;script&gt;" in html
            assert "<script>" not in html

    @pytest.mark.asyncio
    async def test_empty_state_no_messages(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.list_messages = AsyncMock(return_value=([], 0))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            assert "No messages found" in resp.text

    @pytest.mark.asyncio
    async def test_empty_state_with_search_filter(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.list_messages = AsyncMock(return_value=([], 0))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages?search=foo")
            assert "No messages match your search criteria" in resp.text

    @pytest.mark.asyncio
    async def test_count_header_with_pagination(self, setup_tenant_manager):
        from src.main import app

        msgs = [_make_message(id=i, message_id=f"msg_{i}") for i in range(3)]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 100))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            assert "Showing 3 of 100 messages" in resp.text

    @pytest.mark.asyncio
    async def test_chat_jid_filter_passed_to_db(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.list_messages = AsyncMock(return_value=([], 0))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await client.get("/admin/fragments/messages?chat_jid=abc%40g.us")
            setup_tenant_manager._db.list_messages.assert_called()
            call_kwargs = setup_tenant_manager._db.list_messages.call_args.kwargs
            assert call_kwargs["chat_jid"] == "abc@g.us"

    @pytest.mark.asyncio
    async def test_search_term_highlighting(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                text="Hello World",
                message_id="msg_hl",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages?search=world")
            html = resp.text
            assert "<mark" in html

    @pytest.mark.asyncio
    async def test_media_type_badge(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                msg_type="image",
                media_url="https://example.com/img.jpg",
                message_id="msg_media",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "text-green-400" in html
            assert "image" in html


class TestMessagesTabsFragment:
    @pytest.mark.asyncio
    async def test_tabs_returns_all_button(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.get_recent_chat_tabs = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages-tabs")
            assert resp.status_code == 200
            html = resp.text
            assert "All" in html
            assert "bg-whatsapp" in html

    @pytest.mark.asyncio
    async def test_tabs_shows_contact_buttons(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.get_recent_chat_tabs = AsyncMock(
            return_value=[
                {"chat_jid": "123@s.whatsapp.net", "name": "Alice", "is_group": False},
                {"chat_jid": "abc@g.us", "name": "Family", "is_group": True},
            ]
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages-tabs")
            html = resp.text
            assert "Alice" in html
            assert "Family" in html
            assert "switchChatTab" in html

    @pytest.mark.asyncio
    async def test_tabs_filters_by_tenant(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.get_recent_chat_tabs = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            await client.get("/admin/fragments/messages-tabs?tenant_hash=hash_1")
            setup_tenant_manager._db.get_recent_chat_tabs.assert_called_once()
            call_kwargs = setup_tenant_manager._db.get_recent_chat_tabs.call_args.kwargs
            assert call_kwargs["tenant_hash"] == "hash_1"

    @pytest.mark.asyncio
    async def test_tabs_no_db_returns_fallback(self, setup_tenant_manager):
        from src.admin.routes import get_messages_tabs_fragment

        setup_tenant_manager._db = None
        resp = await get_messages_tabs_fragment(session_id="test")
        html = resp.body.decode() if isinstance(resp.body, bytes) else resp.body
        assert "All" in html

    @pytest.mark.asyncio
    async def test_tabs_escaping_special_chars(self, setup_tenant_manager):
        from src.main import app

        setup_tenant_manager._db.get_recent_chat_tabs = AsyncMock(
            return_value=[
                {
                    "chat_jid": "123@s.whatsapp.net",
                    "name": "O'Brien's",
                    "is_group": False,
                },
            ]
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages-tabs")
            html = resp.text
            assert "O'Brien" in html or "O&#39;Brien" in html or "O\\'Brien" in html


class TestMessagesPageStructure:
    @pytest.mark.asyncio
    async def test_page_has_tabs_container(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/messages")
            assert resp.status_code == 200
            assert 'id="messages-tabs-container"' in resp.text
            assert 'hx-get="/admin/fragments/messages-tabs"' in resp.text

    @pytest.mark.asyncio
    async def test_page_has_reply_modal(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/messages")
            html = resp.text
            assert 'id="reply-modal"' in html
            assert 'id="reply-text"' in html
            assert 'id="reply-tenant"' in html
            assert "Cancel" in html
            assert "Send" in html

    @pytest.mark.asyncio
    async def test_page_has_reply_js_functions(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/messages")
            html = resp.text
            assert "openReplyModal" in html
            assert "closeReplyModal" in html
            assert "sendReply" in html
            assert "showToast" in html

    @pytest.mark.asyncio
    async def test_page_has_tab_switching_js(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/messages")
            html = resp.text
            assert "switchChatTab" in html
            assert "selectedChatJid" in html
            assert "fetchTabs" in html
            assert "onTenantFilterChange" in html

    @pytest.mark.asyncio
    async def test_tenant_dropdown_uses_onTenantFilterChange(
        self, setup_tenant_manager
    ):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/messages")
            assert "onTenantFilterChange()" in resp.text

    @pytest.mark.asyncio
    async def test_page_requires_auth(self):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/admin/messages",
                follow_redirects=False,
                headers={"Accept": "text/html"},
            )
            assert resp.status_code == 302
            assert resp.headers["location"] == "/admin/login"


class TestOutboundLabelDisplay:
    @pytest.mark.asyncio
    async def test_outbound_shows_to_not_from(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                from_jid="9876543210@s.whatsapp.net",
                chat_jid="5551234567@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={}
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To: 5551234567" in html
            assert "From: 9876543210" not in html

    @pytest.mark.asyncio
    async def test_outbound_with_contact_name_shows_name(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="5551234567@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={
                (tenant.api_key_hash, "5551234567@s.whatsapp.net"): {
                    "name": "John Doe",
                    "is_group": False,
                }
            }
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To: John Doe" in html

    @pytest.mark.asyncio
    async def test_outbound_without_contact_shows_phone(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="5559998888@s.whatsapp.net",
                push_name="",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={}
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To: 5559998888" in html

    @pytest.mark.asyncio
    async def test_outbound_contact_name_same_as_phone_shows_phone_only(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="5551234567@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={
                (tenant.api_key_hash, "5551234567@s.whatsapp.net"): {
                    "name": "5551234567",
                    "is_group": False,
                }
            }
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To: 5551234567" in html
            assert "To: 5551234567 (5551234567)" not in html

    @pytest.mark.asyncio
    async def test_outbound_recipient_name_escaped(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="5551234567@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={
                (tenant.api_key_hash, "5551234567@s.whatsapp.net"): {
                    "name": "O'Brien <script>",
                    "is_group": False,
                }
            }
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To:" in html
            assert "<script>" not in html
            assert "&lt;script&gt;" in html

    @pytest.mark.asyncio
    async def test_inbound_still_shows_from(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="inbound",
                push_name="Alice",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "From: Alice" in html
            assert "To:" not in html

    @pytest.mark.asyncio
    async def test_mixed_inbound_outbound_correct_labels(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="inbound",
                push_name="Alice",
                message_id="in_1",
            ),
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="5550001111@s.whatsapp.net",
                message_id="out_1",
            ),
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 2))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "From: Alice" in html
            assert "To: 5550001111" in html

    @pytest.mark.asyncio
    async def test_outbound_group_message_shows_to(
        self, setup_tenant_manager, with_tenant
    ):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                direction="outbound",
                chat_jid="family@g.us",
                is_group=True,
                from_jid="9876543210@s.whatsapp.net",
                push_name="",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))
        setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
            return_value={
                (tenant.api_key_hash, "family@g.us"): {
                    "name": "Family Group",
                    "is_group": True,
                }
            }
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "To:" in html
            assert "Chat: Family Group" in html


class TestPhoneAndChatIdDisplay:
    @pytest.mark.asyncio
    async def test_phone_and_jid_html_escaped(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                chat_jid="555123&<special>@s.whatsapp.net",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text

            assert "555123&amp;&lt;special&gt;" in html
            assert "555123&<special>" not in html.replace(
                'data-chat-jid="555123&<special>@s.whatsapp.net"', ""
            )

    @pytest.mark.asyncio
    async def test_meta_info_styling_classes(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [_make_message(tenant_hash=tenant.api_key_hash)]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert "text-gray-600" in html
            assert "whitespace-nowrap" in html

    @pytest.mark.asyncio
    async def test_chat_jid_without_at_sign(self, setup_tenant_manager, with_tenant):
        from src.main import app

        tenant, _ = with_tenant
        msgs = [
            _make_message(
                tenant_hash=tenant.api_key_hash,
                chat_jid="just_a_plain_id",
            )
        ]
        setup_tenant_manager._db.list_messages = AsyncMock(return_value=(msgs, 1))

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            resp = await client.get("/admin/fragments/messages")
            html = resp.text
            assert ">just_a_plain_id<" in html
