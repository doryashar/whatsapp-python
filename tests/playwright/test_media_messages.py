import pytest
import secrets
import hashlib
from datetime import datetime
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL, get_event_loop

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.tenant import tenant_manager, Tenant
from src.store.database import Database
from src.store.messages import MessageStore, StoredMessage


pytestmark = pytest.mark.playwright


@pytest.fixture
def media_tenant(db_session: Database):
    raw_key = f"wa_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    tenant = Tenant(
        api_key_hash=key_hash,
        name="media_test_tenant",
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
def media_messages(db_session: Database, media_tenant: dict):
    messages = []
    tenant_hash = media_tenant["hash"]
    loop = get_event_loop()
    ts = int(datetime.now().timestamp() * 1000)

    image_msg = StoredMessage(
        id=f"img_msg_{secrets.token_hex(4)}",
        from_jid="1234567890@s.whatsapp.net",
        chat_jid="1234567890@s.whatsapp.net",
        is_group=False,
        push_name="Image Sender",
        text="Check this photo",
        msg_type="image",
        timestamp=ts - 5000,
        direction="inbound",
        media_url="https://example.com/test_image.jpg",
        mimetype="image/jpeg",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=image_msg.id,
            from_jid=image_msg.from_jid,
            chat_jid=image_msg.chat_jid,
            is_group=image_msg.is_group,
            push_name=image_msg.push_name,
            text=image_msg.text,
            msg_type=image_msg.msg_type,
            timestamp=image_msg.timestamp,
            direction=image_msg.direction,
            media_url=image_msg.media_url,
            mimetype=image_msg.mimetype,
        )
    )
    messages.append(image_msg)

    video_msg = StoredMessage(
        id=f"vid_msg_{secrets.token_hex(4)}",
        from_jid="1234567891@s.whatsapp.net",
        chat_jid="1234567891@s.whatsapp.net",
        is_group=False,
        push_name="Video Sender",
        text="Watch this video",
        msg_type="video",
        timestamp=ts - 4000,
        direction="inbound",
        media_url="https://example.com/test_video.mp4",
        mimetype="video/mp4",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=video_msg.id,
            from_jid=video_msg.from_jid,
            chat_jid=video_msg.chat_jid,
            is_group=video_msg.is_group,
            push_name=video_msg.push_name,
            text=video_msg.text,
            msg_type=video_msg.msg_type,
            timestamp=video_msg.timestamp,
            direction=video_msg.direction,
            media_url=video_msg.media_url,
            mimetype=video_msg.mimetype,
        )
    )
    messages.append(video_msg)

    audio_msg = StoredMessage(
        id=f"aud_msg_{secrets.token_hex(4)}",
        from_jid="1234567892@s.whatsapp.net",
        chat_jid="1234567892@s.whatsapp.net",
        is_group=False,
        push_name="Audio Sender",
        text="",
        msg_type="audio",
        timestamp=ts - 3000,
        direction="inbound",
        media_url="https://example.com/test_audio.ogg",
        mimetype="audio/ogg",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=audio_msg.id,
            from_jid=audio_msg.from_jid,
            chat_jid=audio_msg.chat_jid,
            is_group=audio_msg.is_group,
            push_name=audio_msg.push_name,
            text=audio_msg.text or "",
            msg_type=audio_msg.msg_type,
            timestamp=audio_msg.timestamp,
            direction=audio_msg.direction,
            media_url=audio_msg.media_url,
            mimetype=audio_msg.mimetype,
        )
    )
    messages.append(audio_msg)

    doc_msg = StoredMessage(
        id=f"doc_msg_{secrets.token_hex(4)}",
        from_jid="1234567893@s.whatsapp.net",
        chat_jid="1234567893@s.whatsapp.net",
        is_group=False,
        push_name="Doc Sender",
        text="Here's the report",
        msg_type="document",
        timestamp=ts - 2000,
        direction="inbound",
        media_url="https://example.com/test_doc.pdf",
        mimetype="application/pdf",
        filename="Report_2024.pdf",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=doc_msg.id,
            from_jid=doc_msg.from_jid,
            chat_jid=doc_msg.chat_jid,
            is_group=doc_msg.is_group,
            push_name=doc_msg.push_name,
            text=doc_msg.text,
            msg_type=doc_msg.msg_type,
            timestamp=doc_msg.timestamp,
            direction=doc_msg.direction,
            media_url=doc_msg.media_url,
            mimetype=doc_msg.mimetype,
            filename=doc_msg.filename,
        )
    )
    messages.append(doc_msg)

    loc_msg = StoredMessage(
        id=f"loc_msg_{secrets.token_hex(4)}",
        from_jid="1234567894@s.whatsapp.net",
        chat_jid="1234567894@s.whatsapp.net",
        is_group=False,
        push_name="Location Sender",
        text="",
        msg_type="location",
        timestamp=ts - 1000,
        direction="inbound",
        latitude=37.7749,
        longitude=-122.4194,
        location_name="San Francisco",
        location_address="California St",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=loc_msg.id,
            from_jid=loc_msg.from_jid,
            chat_jid=loc_msg.chat_jid,
            is_group=loc_msg.is_group,
            push_name=loc_msg.push_name,
            text=loc_msg.text or "",
            msg_type=loc_msg.msg_type,
            timestamp=loc_msg.timestamp,
            direction=loc_msg.direction,
            latitude=loc_msg.latitude,
            longitude=loc_msg.longitude,
            location_name=loc_msg.location_name,
            location_address=loc_msg.location_address,
        )
    )
    messages.append(loc_msg)

    text_msg = StoredMessage(
        id=f"txt_msg_{secrets.token_hex(4)}",
        from_jid="1234567895@s.whatsapp.net",
        chat_jid="1234567895@s.whatsapp.net",
        is_group=False,
        push_name="Text Sender",
        text="Plain text message",
        msg_type="text",
        timestamp=ts,
        direction="inbound",
    )
    loop.run_until_complete(
        db_session.save_message(
            tenant_hash=tenant_hash,
            message_id=text_msg.id,
            from_jid=text_msg.from_jid,
            chat_jid=text_msg.chat_jid,
            is_group=text_msg.is_group,
            push_name=text_msg.push_name,
            text=text_msg.text,
            msg_type=text_msg.msg_type,
            timestamp=text_msg.timestamp,
            direction=text_msg.direction,
        )
    )
    messages.append(text_msg)

    yield messages

    loop.run_until_complete(db_session.clear_tenant_messages(tenant_hash))


class TestMediaMessageRendering:
    def test_image_message_renders_with_preview(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        img_tag = authenticated_page.locator('img[src*="example.com"]')
        expect(img_tag.first).to_be_visible(timeout=5000)

    def test_image_has_download_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        download_link = authenticated_page.locator('a:has-text("Download")')
        expect(download_link.first).to_be_visible(timeout=5000)

    def test_video_message_renders_with_player(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        video_tag = authenticated_page.locator("video")
        expect(video_tag.first).to_be_visible(timeout=5000)

    def test_video_has_controls(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        video = authenticated_page.locator("video[controls]")
        expect(video.first).to_be_visible(timeout=5000)

    def test_audio_message_renders_with_player(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        audio_tag = authenticated_page.locator("audio")
        expect(audio_tag.first).to_be_visible(timeout=5000)

    def test_audio_has_download_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        audio_download = authenticated_page.locator('a:has-text("Download Audio")')
        expect(audio_download.first).to_be_visible(timeout=5000)

    def test_document_message_renders_with_filename(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        filename = authenticated_page.locator("text=Report_2024.pdf")
        expect(filename).to_be_visible(timeout=5000)

    def test_document_has_clickable_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        doc_link = authenticated_page.locator('a[href*="test_doc.pdf"]')
        expect(doc_link).to_be_visible(timeout=5000)

    def test_location_message_renders_with_name(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        location_name = authenticated_page.locator("text=San Francisco")
        expect(location_name).to_be_visible(timeout=5000)

    def test_location_has_google_maps_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        maps_link = authenticated_page.locator('a[href*="maps.google.com"]')
        expect(maps_link).to_be_visible(timeout=5000)

    def test_text_message_renders_normally(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        text_content = authenticated_page.locator("text=Plain text message")
        expect(text_content).to_be_visible(timeout=5000)


class TestMediaTypeBadges:
    def test_image_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        image_badge = authenticated_page.locator("text=/image/i")
        expect(image_badge.first).to_be_visible(timeout=5000)

    def test_video_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        video_badge = authenticated_page.locator("text=/video/i")
        expect(video_badge.first).to_be_visible(timeout=5000)

    def test_audio_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        audio_badge = authenticated_page.locator("text=/audio/i")
        expect(audio_badge.first).to_be_visible(timeout=5000)

    def test_document_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        doc_badge = authenticated_page.locator("text=/document/i")
        expect(doc_badge.first).to_be_visible(timeout=5000)

    def test_location_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        loc_badge = authenticated_page.locator("text=/location/i")
        expect(loc_badge.first).to_be_visible(timeout=5000)


class TestMediaCaptions:
    def test_image_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        caption = authenticated_page.locator("text=Check this photo")
        expect(caption).to_be_visible(timeout=5000)

    def test_video_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        caption = authenticated_page.locator("text=Watch this video")
        expect(caption).to_be_visible(timeout=5000)

    def test_document_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        caption = authenticated_page.locator("text=Here's the report")
        expect(caption).to_be_visible(timeout=5000)


class TestTenantPanelMedia:
    def test_tenant_panel_shows_image_message(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}"
        )

        img_tag = authenticated_page.locator('img[src*="example.com"]')
        expect(img_tag.first).to_be_visible(timeout=5000)

    def test_tenant_panel_shows_video_message(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}"
        )

        video_tag = authenticated_page.locator("video")
        expect(video_tag.first).to_be_visible(timeout=5000)

    def test_tenant_panel_shows_location_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}"
        )

        maps_link = authenticated_page.locator('a[href*="maps.google.com"]')
        expect(maps_link).to_be_visible(timeout=5000)


class TestMediaLinksOpenNewTab:
    def test_image_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        img_link = authenticated_page.locator(
            'a[href*="test_image.jpg"][target="_blank"]'
        )
        expect(img_link.first).to_be_visible(timeout=5000)

    def test_document_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        doc_link = authenticated_page.locator(
            'a[href*="test_doc.pdf"][target="_blank"]'
        )
        expect(doc_link).to_be_visible(timeout=5000)

    def test_maps_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        maps_link = authenticated_page.locator(
            'a[href*="maps.google.com"][target="_blank"]'
        )
        expect(maps_link).to_be_visible(timeout=5000)


class TestMixedMessagesDisplay:
    def test_all_message_types_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        authenticated_page.wait_for_timeout(1000)

        expect(authenticated_page.locator("img").first).to_be_visible(timeout=5000)
        expect(authenticated_page.locator("video").first).to_be_visible(timeout=5000)
        expect(authenticated_page.locator("audio").first).to_be_visible(timeout=5000)

    def test_text_message_not_broken_by_media(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        authenticated_page.goto(f"{BASE_URL}/admin/messages")

        text_msg = authenticated_page.locator("text=Plain text message")
        expect(text_msg).to_be_visible(timeout=5000)
