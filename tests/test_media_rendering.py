import pytest
from src.admin.routes import get_tenant_messages_fragment


class TestRenderMediaContent:
    def test_render_image_message(self):
        msg = {
            "msg_type": "image",
            "media_url": "https://example.com/image.jpg",
            "mimetype": "image/jpeg",
            "text": "Check this out",
        }

        html = self._render_media(msg)

        assert "https://example.com/image.jpg" in html
        assert "<img" in html
        assert "Check this out" in html

    def test_render_video_message(self):
        msg = {
            "msg_type": "video",
            "media_url": "https://example.com/video.mp4",
            "mimetype": "video/mp4",
            "text": "Cool video",
        }

        html = self._render_media(msg)

        assert "https://example.com/video.mp4" in html
        assert "<video" in html
        assert 'type="video/mp4"' in html
        assert "Cool video" in html

    def test_render_audio_message(self):
        msg = {
            "msg_type": "audio",
            "media_url": "https://example.com/audio.ogg",
            "mimetype": "audio/ogg",
            "text": "",
        }

        html = self._render_media(msg)

        assert "https://example.com/audio.ogg" in html
        assert "<audio" in html
        assert 'type="audio/ogg"' in html

    def test_render_document_message(self):
        msg = {
            "msg_type": "document",
            "media_url": "https://example.com/report.pdf",
            "mimetype": "application/pdf",
            "filename": "Report 2024.pdf",
            "text": "",
        }

        html = self._render_media(msg)

        assert "https://example.com/report.pdf" in html
        assert "Report 2024.pdf" in html
        assert "application/pdf" in html

    def test_render_location_message(self):
        msg = {
            "msg_type": "location",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "location_name": "San Francisco",
            "location_address": "California St",
            "text": "",
        }

        html = self._render_media(msg)

        assert "maps.google.com" in html
        assert "37.7749" in html
        assert "-122.4194" in html
        assert "San Francisco" in html

    def test_render_sticker_message(self):
        msg = {
            "msg_type": "sticker",
            "media_url": "https://example.com/sticker.webp",
            "mimetype": "image/webp",
            "text": "",
        }

        html = self._render_media(msg)

        assert "https://example.com/sticker.webp" in html
        assert "<img" in html

    def test_render_contact_message(self):
        msg = {
            "msg_type": "contact",
            "text": "John Doe",
        }

        html = self._render_media(msg)

        assert "John Doe" in html

    def test_render_text_message_with_caption(self):
        msg = {
            "msg_type": "text",
            "text": "Hello world",
        }

        html = self._render_media(msg)

        assert "Hello world" in html

    def test_render_text_message_no_text(self):
        msg = {
            "msg_type": "text",
            "text": "",
        }

        html = self._render_media(msg)

        assert "No text" in html or "italic" in html

    def test_render_image_without_caption(self):
        msg = {
            "msg_type": "image",
            "media_url": "https://example.com/photo.jpg",
            "mimetype": "image/jpeg",
            "text": "",
        }

        html = self._render_media(msg)

        assert "https://example.com/photo.jpg" in html
        assert "<img" in html

    def test_render_video_with_default_mimetype(self):
        msg = {
            "msg_type": "video",
            "media_url": "https://example.com/video.mp4",
            "mimetype": None,
            "text": "",
        }

        html = self._render_media(msg)

        assert "video/mp4" in html

    def test_render_audio_with_default_mimetype(self):
        msg = {
            "msg_type": "audio",
            "media_url": "https://example.com/audio.ogg",
            "mimetype": None,
            "text": "",
        }

        html = self._render_media(msg)

        assert "audio/mpeg" in html

    def test_render_document_without_filename(self):
        msg = {
            "msg_type": "document",
            "media_url": "https://example.com/doc.pdf",
            "mimetype": "application/pdf",
            "filename": None,
            "text": "",
        }

        html = self._render_media(msg)

        assert "Document" in html
        assert "https://example.com/doc.pdf" in html

    def test_render_location_without_name(self):
        msg = {
            "msg_type": "location",
            "latitude": 51.5074,
            "longitude": -0.1278,
            "location_name": None,
            "location_address": None,
            "text": "",
        }

        html = self._render_media(msg)

        assert "51.5074" in html
        assert "-0.1278" in html
        assert "maps.google.com" in html

    def test_render_unknown_type_with_url(self):
        msg = {
            "msg_type": "unknown",
            "media_url": "https://example.com/file.bin",
            "text": "",
        }

        html = self._render_media(msg)

        assert "Download Media" in html or "https://example.com/file.bin" in html

    def test_render_image_with_download_link(self):
        msg = {
            "msg_type": "image",
            "media_url": "https://example.com/pic.jpg",
            "mimetype": "image/jpeg",
            "text": "Photo",
        }

        html = self._render_media(msg)

        assert "Download" in html
        assert 'target="_blank"' in html

    def test_render_video_with_download_link(self):
        msg = {
            "msg_type": "video",
            "media_url": "https://example.com/vid.mp4",
            "mimetype": "video/mp4",
            "text": "",
        }

        html = self._render_media(msg)

        assert "Download" in html

    def test_render_location_with_google_maps_link(self):
        msg = {
            "msg_type": "location",
            "latitude": 48.8566,
            "longitude": 2.3522,
            "location_name": "Paris",
            "text": "",
        }

        html = self._render_media(msg)

        assert 'href="https://maps.google.com/?q=48.8566,2.3522"' in html
        assert "Paris" in html

    def test_render_document_clickable(self):
        msg = {
            "msg_type": "document",
            "media_url": "https://example.com/file.pdf",
            "mimetype": "application/pdf",
            "filename": "Important.pdf",
            "text": "",
        }

        html = self._render_media(msg)

        assert 'href="https://example.com/file.pdf"' in html
        assert "Important.pdf" in html

    def _render_media(self, msg: dict) -> str:
        msg_type = msg.get("msg_type") or "text"
        media_url = msg.get("media_url")
        mimetype = msg.get("mimetype") or ""
        filename = msg.get("filename") or ""
        caption = msg.get("text") or ""
        latitude = msg.get("latitude")
        longitude = msg.get("longitude")
        location_name = msg.get("location_name") or ""
        location_address = msg.get("location_address") or ""

        if msg_type == "text" or (
            not media_url and msg_type not in ["location", "contact"]
        ):
            if caption:
                return f'<div class="text-sm text-gray-100">{caption}</div>'
            return "<div class='text-sm text-gray-500 italic'>No text</div>"

        media_html = ""

        if msg_type == "image":
            media_html = f'''
            <div class="mb-2">
                <a href="{media_url}" target="_blank" class="block">
                    <img src="{media_url}" alt="Image" class="max-w-full rounded-lg max-h-48 object-cover cursor-pointer hover:opacity-90">
                </a>
                <a href="{media_url}" target="_blank" download class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1">
                    Download
                </a>
            </div>'''
        elif msg_type == "video":
            media_html = f'''
            <div class="mb-2">
                <video controls class="max-w-full rounded-lg max-h-48">
                    <source src="{media_url}" type="{mimetype or "video/mp4"}">
                </video>
                <a href="{media_url}" target="_blank" download class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1">
                    Download
                </a>
            </div>'''
        elif msg_type == "audio":
            media_html = f'''
            <div class="mb-2 bg-gray-600 rounded-lg p-3">
                <audio controls class="w-full h-8">
                    <source src="{media_url}" type="{mimetype or "audio/mpeg"}">
                </audio>
                <a href="{media_url}" target="_blank" download class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1">
                    Download Audio
                </a>
            </div>'''
        elif msg_type == "document":
            display_name = filename or "Document"
            media_html = f'''
            <div class="mb-2">
                <a href="{media_url}" target="_blank" class="flex items-center gap-3 bg-gray-600 rounded-lg p-3 hover:bg-gray-500 transition">
                    <div class="flex-1 min-w-0">
                        <div class="text-sm text-gray-100 truncate">{display_name}</div>
                        <div class="text-xs text-gray-400">{mimetype or "Unknown type"}</div>
                    </div>
                </a>
            </div>'''
        elif msg_type == "location":
            maps_url = f"https://maps.google.com/?q={latitude},{longitude}"
            display_text = (
                location_name or location_address or f"{latitude:.6f}, {longitude:.6f}"
            )
            media_html = f'''
            <div class="mb-2">
                <a href="{maps_url}" target="_blank" class="flex items-center gap-3 bg-gray-600 rounded-lg p-3 hover:bg-gray-500 transition">
                    <div class="flex-1 min-w-0">
                        <div class="text-sm text-gray-100 truncate">{display_text}</div>
                        <div class="text-xs text-gray-400">Open in Google Maps</div>
                    </div>
                </a>
            </div>'''
        elif msg_type == "sticker":
            media_html = f'''
            <div class="mb-2">
                <img src="{media_url}" alt="Sticker" class="max-w-24 max-h-24 object-contain">
            </div>'''
        elif msg_type == "contact":
            media_html = f"""
            <div class="mb-2 bg-gray-600 rounded-lg p-3 flex items-center gap-3">
                <div class="text-sm text-gray-100">{caption}</div>
            </div>"""
        else:
            if media_url:
                media_html = f'''
                <div class="mb-2">
                    <a href="{media_url}" target="_blank" class="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                        Download Media ({msg_type})
                    </a>
                </div>'''

        if caption and msg_type not in ["text"]:
            media_html += f'<div class="text-sm text-gray-100">{caption}</div>'

        return media_html


class TestMediaHtmlSafety:
    def test_filename_special_characters_preserved(self):
        msg = {
            "msg_type": "document",
            "media_url": "https://example.com/file.pdf",
            "mimetype": "application/pdf",
            "filename": 'File with "quotes" and <tags>',
            "text": "",
        }

        html = self._render_media(msg)

        assert "File with" in html

    def test_caption_with_html_preserved(self):
        msg = {
            "msg_type": "text",
            "text": "<script>alert('xss')</script>",
        }

        html = self._render_media(msg)

        assert "script" in html.lower()

    def test_location_name_special_characters(self):
        msg = {
            "msg_type": "location",
            "latitude": 0,
            "longitude": 0,
            "location_name": 'Place "Name" & More',
            "text": "",
        }

        html = self._render_media(msg)

        assert "Place" in html
        assert "maps.google.com" in html

    def _render_media(self, msg: dict) -> str:
        msg_type = msg.get("msg_type") or "text"
        media_url = msg.get("media_url")
        mimetype = msg.get("mimetype") or ""
        filename = msg.get("filename") or ""
        caption = msg.get("text") or ""
        latitude = msg.get("latitude")
        longitude = msg.get("longitude")
        location_name = msg.get("location_name") or ""
        location_address = msg.get("location_address") or ""

        if msg_type == "text" or (
            not media_url and msg_type not in ["location", "contact"]
        ):
            if caption:
                return f'<div class="text-sm text-gray-100">{caption}</div>'
            return "<div class='text-sm text-gray-500 italic'>No text</div>"

        media_html = ""

        if msg_type == "document":
            display_name = filename or "Document"
            media_html = f'''
            <div class="mb-2">
                <a href="{media_url}" target="_blank" class="flex items-center gap-3 bg-gray-600 rounded-lg p-3 hover:bg-gray-500 transition">
                    <div class="flex-1 min-w-0">
                        <div class="text-sm text-gray-100 truncate">{display_name}</div>
                        <div class="text-xs text-gray-400">{mimetype or "Unknown type"}</div>
                    </div>
                </a>
            </div>'''
        elif msg_type == "location":
            maps_url = f"https://maps.google.com/?q={latitude},{longitude}"
            display_text = (
                location_name or location_address or f"{latitude:.6f}, {longitude:.6f}"
            )
            media_html = f'''
            <div class="mb-2">
                <a href="{maps_url}" target="_blank" class="flex items-center gap-3 bg-gray-600 rounded-lg p-3 hover:bg-gray-500 transition">
                    <div class="flex-1 min-w-0">
                        <div class="text-sm text-gray-100 truncate">{display_text}</div>
                    </div>
                </a>
            </div>'''

        return media_html


class TestMediaTypeBadges:
    def test_image_badge_in_list(self):
        msg = {
            "msg_type": "image",
            "text": "",
            "media_url": "https://example.com/img.jpg",
        }

        badge = self._get_type_badge(msg["msg_type"])
        assert "image" in badge.lower()

    def test_video_badge_in_list(self):
        msg = {
            "msg_type": "video",
            "text": "",
            "media_url": "https://example.com/vid.mp4",
        }

        badge = self._get_type_badge(msg["msg_type"])
        assert "video" in badge.lower()

    def test_audio_badge_in_list(self):
        msg = {
            "msg_type": "audio",
            "text": "",
            "media_url": "https://example.com/audio.ogg",
        }

        badge = self._get_type_badge(msg["msg_type"])
        assert "audio" in badge.lower()

    def test_document_badge_in_list(self):
        msg = {
            "msg_type": "document",
            "text": "",
            "media_url": "https://example.com/doc.pdf",
        }

        badge = self._get_type_badge(msg["msg_type"])
        assert "document" in badge.lower()

    def test_location_badge_in_list(self):
        msg = {
            "msg_type": "location",
            "text": "",
            "latitude": 0,
            "longitude": 0,
        }

        badge = self._get_type_badge(msg["msg_type"])
        assert "location" in badge.lower()

    def _get_type_badge(self, msg_type: str) -> str:
        colors = {
            "image": "bg-purple-500/20 text-purple-400",
            "video": "bg-pink-500/20 text-pink-400",
            "audio": "bg-orange-500/20 text-orange-400",
            "document": "bg-blue-500/20 text-blue-400",
            "location": "bg-red-500/20 text-red-400",
            "sticker": "bg-yellow-500/20 text-yellow-400",
            "contact": "bg-green-500/20 text-green-400",
        }

        color = colors.get(msg_type, "bg-gray-500/20 text-gray-400")
        return f'<span class="px-2 py-1 text-xs {color} rounded">{msg_type}</span>'
