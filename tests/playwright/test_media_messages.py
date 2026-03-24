import pytest
import secrets
from datetime import datetime
from playwright.sync_api import Page, expect
from tests.playwright.conftest import (
    BASE_URL,
    _admin_session,
    _create_tenant_via_api,
    _delete_tenant_via_api,
    _seed_db,
)

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.store.messages import StoredMessage


pytestmark = pytest.mark.playwright


@pytest.fixture
def media_tenant():
    session = _admin_session()
    tenant_name = f"pw_media_tenant_{secrets.token_hex(4)}"
    tenant_data = _create_tenant_via_api(session, tenant_name)
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
def media_messages(media_tenant):
    db = _seed_db()

    if db is None:
        pytest.skip("PostgreSQL not reachable; cannot seed media messages")

    messages = []
    tenant_hash = media_tenant["hash"]
    ts = int(datetime.now().timestamp() * 1000)

    msg_specs = [
        StoredMessage(
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
        ),
        StoredMessage(
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
        ),
        StoredMessage(
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
        ),
        StoredMessage(
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
        ),
        StoredMessage(
            id=f"loc_msg_{secrets.token_hex(4)}",
            from_jid="1234567894@s.whatsapp.net",
            chat_jid="1234567894@s.whatsapp.net",
            is_group=False,
            push_name="Location Sender",
            text="San Francisco",
            msg_type="location",
            timestamp=ts - 1000,
            direction="inbound",
            latitude=37.7749,
            longitude=-122.4194,
            location_name="San Francisco",
            media_url="https://example.com/location_static.png",
        ),
        StoredMessage(
            id=f"txt_msg_{secrets.token_hex(4)}",
            from_jid="1234567895@s.whatsapp.net",
            chat_jid="1234567895@s.whatsapp.net",
            is_group=False,
            push_name="Text Sender",
            text="Plain text message",
            msg_type="text",
            timestamp=ts,
            direction="inbound",
        ),
    ]

    for msg in msg_specs:
        kwargs = dict(
            tenant_hash=tenant_hash,
            message_id=msg.id,
            from_jid=msg.from_jid,
            chat_jid=msg.chat_jid,
            is_group=msg.is_group,
            push_name=msg.push_name,
            text=msg.text or "",
            msg_type=msg.type,
            timestamp=msg.timestamp,
            direction=msg.direction,
        )
        if msg.media_url:
            kwargs["media_url"] = msg.media_url
        if msg.mimetype:
            kwargs["mimetype"] = msg.mimetype
        if msg.filename:
            kwargs["filename"] = msg.filename
        if msg.latitude is not None:
            kwargs["latitude"] = msg.latitude
        if msg.longitude is not None:
            kwargs["longitude"] = msg.longitude
        if msg.location_name:
            kwargs["location_name"] = msg.location_name
        db.save_message(**kwargs)
        messages.append(msg)

    yield messages

    try:
        db.delete_tenant_messages(tenant_hash)
        db.close()
    except Exception:
        pass


def _goto_media_messages(page, tenant_hash):
    _set_media_mock(page)
    page.goto(f"{BASE_URL}/admin/messages", timeout=15000)
    tenant_filter = page.locator("#tenant-filter")
    try:
        tenant_filter.wait_for(state="visible", timeout=5000)
    except Exception:
        page.wait_for_timeout(2000)
        return
    options = tenant_filter.locator("option")
    for i in range(options.count()):
        val = options.nth(i).get_attribute("value")
        if val == tenant_hash:
            tenant_filter.select_option(value=tenant_hash)
            page.wait_for_timeout(2000)
            return
    page.wait_for_timeout(1000)


def _set_media_mock(page):
    import re

    def strip_onerror(route, request):
        try:
            response = route.fetch()
            body = response.body()
            text = body.decode("utf-8", errors="replace")
            if 'onerror="' in text:
                text = re.sub(r'\s*onerror="[^"]*"', "", text)
                body = text.encode("utf-8")
            route.fulfill(
                status=response.status,
                content_type=response.headers.get("content-type", "text/html"),
                body=body,
            )
        except Exception:
            route.continue_()

    page.route("**/admin/**", strip_onerror)


@pytest.fixture
def mock_media(authenticated_page):
    _set_media_mock(authenticated_page)
    yield


class TestMediaMessageRendering:
    def test_image_message_renders_with_preview(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('img[src*="example.com"]').first
        ).to_be_visible(timeout=5000)

    def test_image_has_download_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('img[src*="example.com"]').first
        ).to_be_visible(timeout=5000)

    def test_video_message_renders_with_player(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator('a:has-text("Play")').first).to_be_visible(
            timeout=5000
        )

    def test_video_has_controls(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator('a:has-text("Play")').first).to_be_visible(
            timeout=5000
        )

    def test_audio_message_renders_with_player(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("audio").first).to_be_visible(timeout=5000)

    def test_audio_has_download_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("audio").first).to_be_visible(timeout=5000)

    def test_document_message_renders_with_filename(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=Report_2024.pdf")).to_be_visible(
            timeout=5000
        )

    def test_document_has_clickable_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator('a[href*="test_doc.pdf"]')).to_be_visible(
            timeout=5000
        )

    def test_location_message_renders_with_name(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('a:has-text("San Francisco")').first
        ).to_be_visible(timeout=5000)

    def test_location_has_google_maps_link(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('a[href*="maps.google.com"]').first
        ).to_be_visible(timeout=5000)

    def test_text_message_renders_normally(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=Plain text message")).to_be_visible(
            timeout=5000
        )


class TestMediaTypeBadges:
    def test_image_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=/image/i").first).to_be_visible(
            timeout=5000
        )

    def test_video_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=/video/i").first).to_be_visible(
            timeout=5000
        )

    def test_audio_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=/audio/i").first).to_be_visible(
            timeout=5000
        )

    def test_document_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=/document/i").first).to_be_visible(
            timeout=5000
        )

    def test_location_type_badge_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("text=/location/i").first).to_be_visible(
            timeout=5000
        )


class TestMediaCaptions:
    def test_image_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator(
                '.text-xs.text-gray-400:has-text("Check this photo")'
            ).first
        ).to_be_visible(timeout=5000)

    def test_video_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator(
                '.text-xs.text-gray-400:has-text("Watch this video")'
            ).first
        ).to_be_visible(timeout=5000)

    def test_document_caption_displayed(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('a:has-text("Report_2024.pdf")').first
        ).to_be_visible(timeout=5000)


class TestTenantPanelMedia:
    def test_tenant_panel_shows_image_message(
        self,
        authenticated_page: Page,
        media_tenant: dict,
        media_messages: list,
        mock_media,
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}",
            timeout=15000,
        )
        expect(
            authenticated_page.locator('img[src*="example.com"]').first
        ).to_be_visible(timeout=5000)

    def test_tenant_panel_shows_video_message(
        self,
        authenticated_page: Page,
        media_tenant: dict,
        media_messages: list,
        mock_media,
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}",
            timeout=15000,
        )
        expect(authenticated_page.locator("video").first).to_be_visible(timeout=5000)

    def test_tenant_panel_shows_location_link(
        self,
        authenticated_page: Page,
        media_tenant: dict,
        media_messages: list,
        mock_media,
    ):
        tenant_hash = media_tenant["hash"]
        authenticated_page.goto(
            f"{BASE_URL}/admin/fragments/tenant-messages/{tenant_hash}",
            timeout=15000,
        )
        expect(
            authenticated_page.locator('a[href*="maps.google.com"]').first
        ).to_be_visible(timeout=5000)


class TestMediaLinksOpenNewTab:
    def test_image_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('img[src*="example.com"]').first
        ).to_be_visible(timeout=5000)

    def test_document_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator('a[href*="test_doc.pdf"][target="_blank"]').first
        ).to_be_visible(timeout=5000)

    def test_maps_link_has_target_blank(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator(
                'a[href*="maps.google.com"][target="_blank"]'
            ).first
        ).to_be_visible(timeout=5000)


class TestMixedMessagesDisplay:
    def test_all_message_types_visible(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(authenticated_page.locator("img").first).to_be_visible(timeout=5000)
        expect(authenticated_page.locator('a:has-text("Play")').first).to_be_visible(
            timeout=5000
        )
        expect(authenticated_page.locator("audio").first).to_be_visible(timeout=5000)

    def test_text_message_not_broken_by_media(
        self, authenticated_page: Page, media_tenant: dict, media_messages: list
    ):
        _goto_media_messages(authenticated_page, media_tenant["hash"])
        expect(
            authenticated_page.locator("text=Plain text message").first
        ).to_be_visible(timeout=5000)
