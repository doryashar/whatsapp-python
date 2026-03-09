#!/usr/bin/env python3
"""
Integration tests for opencode webhook handler.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@pytest.fixture
def client(test_db, monkeypatch):
    """Create a test client with mocked dependencies."""
    monkeypatch.setenv("SESSION_DB_PATH", test_db)
    monkeypatch.setenv("WHATSAPP_API_URL", "http://localhost:8080")
    monkeypatch.setenv("WHATSAPP_API_KEY", "test_key")
    monkeypatch.setenv("ADMIN_API_KEY", "admin123")
    monkeypatch.setenv("OPENCODE_TIMEOUT", "10")

    from scripts.sample_integration.opencode_webhook_handler import app, session_manager

    with TestClient(app) as client:
        yield client


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "opencode-webhook"}


class TestWebhookEndpoint:
    """Tests for webhook endpoint."""

    @patch("scripts.sample_integration.opencode_webhook_handler.process_message")
    def test_webhook_accepts_message_event(self, mock_process, client):
        """Test webhook accepts message events."""
        event = {
            "type": "message",
            "data": {
                "chat_jid": "1234567890@s.whatsapp.net",
                "text": "Hello",
                "type": "text",
                "from_me": False,
            },
            "timestamp": 1234567890,
        }

        response = client.post("/webhook", json=event)

        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}
        mock_process.assert_called_once()

    def test_webhook_ignores_non_message_events(self, client):
        """Test webhook ignores non-message events."""
        event = {
            "type": "connected",
            "data": {"jid": "test@s.whatsapp.net"},
            "timestamp": 1234567890,
        }

        response = client.post("/webhook", json=event)

        assert response.status_code == 200
        assert response.json() == {"status": "ignored"}


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    def test_list_sessions_unauthorized(self, client):
        """Test list sessions without valid API key."""
        response = client.get("/sessions")
        assert response.status_code in [403, 422]

        response = client.get("/sessions", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

    def test_list_sessions_authorized(self, client):
        """Test list sessions with valid API key."""
        response = client.get("/sessions", headers={"X-API-Key": "admin123"})

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "count" in data
        assert isinstance(data["sessions"], list)

    def test_delete_session_unauthorized(self, client):
        """Test delete session without valid API key."""
        response = client.delete("/sessions/test@s.whatsapp.net")
        assert response.status_code in [403, 422]

        response = client.delete(
            "/sessions/test@s.whatsapp.net", headers={"X-API-Key": "wrong"}
        )
        assert response.status_code == 403

    def test_delete_session_not_found(self, client):
        """Test delete non-existent session."""
        response = client.delete(
            "/sessions/nonexistent@s.whatsapp.net", headers={"X-API-Key": "admin123"}
        )

        assert response.status_code == 404

    def test_cleanup_sessions_unauthorized(self, client):
        """Test cleanup without valid API key."""
        response = client.post("/cleanup?days_old=30")
        assert response.status_code in [403, 422]

        response = client.post("/cleanup?days_old=30", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

    def test_cleanup_sessions_authorized(self, client):
        """Test cleanup with valid API key."""
        response = client.post(
            "/cleanup?days_old=30", headers={"X-API-Key": "admin123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data


class TestMessageProcessing:
    """Tests for message processing logic."""

    @pytest.mark.asyncio
    @patch("scripts.sample_integration.opencode_webhook_handler.run_opencode")
    @patch("scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message")
    async def test_process_text_message_new_session(self, mock_send, mock_opencode):
        """Test processing a text message creates new session."""
        import tempfile
        from scripts.sample_integration.opencode_webhook_handler import (
            process_message,
        )
        from scripts.sample_integration.session_manager import SessionManager
        import scripts.sample_integration.opencode_webhook_handler as handler_module

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            test_session_manager = SessionManager(db_path)
            await test_session_manager.init_db()
            handler_module.session_manager = test_session_manager

            try:
                mock_opencode.return_value = {
                    "text": "Hello! How can I help?",
                    "session_id": "new_session_123",
                }

                message_data = {
                    "chat_jid": "1234567890@s.whatsapp.net",
                    "text": "Hello",
                    "type": "text",
                    "from_me": False,
                }

                await process_message(message_data)

                mock_opencode.assert_called_once()
                call_args = mock_opencode.call_args
                assert call_args.kwargs["message"] == "Hello"
                assert call_args.kwargs["prompt_file"] == "PROMPT.md"

                mock_send.assert_called_once_with(
                    "1234567890@s.whatsapp.net", "Hello! How can I help?"
                )
            finally:
                await test_session_manager.close()
                handler_module.session_manager = None

    @pytest.mark.asyncio
    @patch("scripts.sample_integration.opencode_webhook_handler.run_opencode")
    @patch("scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message")
    async def test_process_message_continues_existing_session(
        self, mock_send, mock_opencode
    ):
        """Test processing message continues existing session."""
        import tempfile
        from scripts.sample_integration.opencode_webhook_handler import (
            process_message,
        )
        from scripts.sample_integration.session_manager import SessionManager
        import scripts.sample_integration.opencode_webhook_handler as handler_module

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            test_session_manager = SessionManager(db_path)
            await test_session_manager.init_db()
            handler_module.session_manager = test_session_manager

            try:
                await test_session_manager.create_session(
                    "1234567890@s.whatsapp.net", "existing_session_456"
                )

                mock_opencode.return_value = {
                    "text": "Continuing our conversation...",
                    "session_id": "existing_session_456",
                }

                message_data = {
                    "chat_jid": "1234567890@s.whatsapp.net",
                    "text": "How are you?",
                    "type": "text",
                    "from_me": False,
                }

                await process_message(message_data)

                mock_opencode.assert_called_once()
                call_args = mock_opencode.call_args
                assert call_args.kwargs["session_id"] == "existing_session_456"
            finally:
                await test_session_manager.close()
                handler_module.session_manager = None

    @pytest.mark.asyncio
    @patch("scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message")
    async def test_process_message_ignores_from_self(self, mock_send):
        """Test that messages from self are ignored."""
        import tempfile
        from scripts.sample_integration.opencode_webhook_handler import (
            process_message,
        )
        from scripts.sample_integration.session_manager import SessionManager
        import scripts.sample_integration.opencode_webhook_handler as handler_module

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            test_session_manager = SessionManager(db_path)
            await test_session_manager.init_db()
            handler_module.session_manager = test_session_manager

            try:
                message_data = {
                    "chat_jid": "1234567890@s.whatsapp.net",
                    "text": "Hello",
                    "type": "text",
                    "from_me": True,
                }

                await process_message(message_data)

                mock_send.assert_not_called()
            finally:
                await test_session_manager.close()
                handler_module.session_manager = None

    @pytest.mark.asyncio
    @patch("scripts.sample_integration.opencode_webhook_handler.send_whatsapp_message")
    async def test_process_message_ignores_missing_chat_jid(self, mock_send):
        """Test that messages without chat_jid are ignored."""
        import tempfile
        from scripts.sample_integration.opencode_webhook_handler import (
            process_message,
        )
        from scripts.sample_integration.session_manager import SessionManager
        import scripts.sample_integration.opencode_webhook_handler as handler_module

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            test_session_manager = SessionManager(db_path)
            await test_session_manager.init_db()
            handler_module.session_manager = test_session_manager

            try:
                message_data = {"text": "Hello", "type": "text", "from_me": False}

                await process_message(message_data)

                mock_send.assert_not_called()
            finally:
                await test_session_manager.close()
                handler_module.session_manager = None


class TestOpenCodeExecution:
    """Tests for OpenCode execution."""

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_run_opencode_new_session(self, mock_subprocess):
        """Test running opencode for new session."""
        from scripts.sample_integration.opencode_webhook_handler import run_opencode

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"type": "response", "data": {"content": "Test response", "session_id": "sess123"}}\n',
                b"",
            )
        )
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        result = await run_opencode(
            message="Hello", prompt_file="PROMPT.md", files=None
        )

        assert "text" in result
        assert "session_id" in result
        assert result["text"] == "Test response"
        assert result["session_id"] == "sess123"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_run_opencode_with_session(self, mock_subprocess):
        """Test running opencode with existing session."""
        from scripts.sample_integration.opencode_webhook_handler import run_opencode

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"type": "response", "data": {"content": "Continued response", "session_id": "existing"}}\n',
                b"",
            )
        )
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        result = await run_opencode(
            message="Continue", session_id="existing", files=None
        )

        assert result["text"] == "Continued response"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_run_opencode_with_files(self, mock_subprocess):
        """Test running opencode with file attachments."""
        from scripts.sample_integration.opencode_webhook_handler import run_opencode

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            temp_file = f.name

        try:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(
                    b'{"type": "response", "data": {"content": "File processed"}}\n',
                    b"",
                )
            )
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await run_opencode(message="Analyze this", files=[temp_file])

            call_args = mock_subprocess.call_args[0]
            assert "-f" in call_args
            assert temp_file in call_args
        finally:
            Path(temp_file).unlink()

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    @patch("asyncio.wait_for")
    async def test_run_opencode_timeout(self, mock_wait_for, mock_subprocess):
        """Test opencode timeout handling."""
        from scripts.sample_integration.opencode_webhook_handler import run_opencode

        mock_wait_for.side_effect = asyncio.TimeoutError()

        result = await run_opencode(message="Test", files=None)

        assert "timed out" in result["text"].lower()
        assert result["session_id"] is None


class TestWhatsAppMessaging:
    """Tests for WhatsApp message sending."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_whatsapp_message_success(self, mock_client):
        """Test sending WhatsApp message successfully."""
        from scripts.sample_integration.opencode_webhook_handler import (
            send_whatsapp_message,
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_context = AsyncMock()
        mock_context.post = AsyncMock(return_value=mock_response)
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()

        mock_client.return_value = mock_context

        await send_whatsapp_message("1234567890@s.whatsapp.net", "Test message")

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_whatsapp_message_truncates_long_message(self, mock_client):
        """Test that long messages are truncated."""
        from scripts.sample_integration.opencode_webhook_handler import (
            send_whatsapp_message,
        )

        long_message = "A" * 5000

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_context = AsyncMock()
        mock_context.post = AsyncMock(return_value=mock_response)
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()

        mock_client.return_value = mock_context

        await send_whatsapp_message("1234567890@s.whatsapp.net", long_message)

        call_args = mock_context.post.call_args
        sent_text = call_args.kwargs["json"]["text"]
        assert len(sent_text) < 5000
        assert "truncated" in sent_text.lower()


class TestMediaHandling:
    """Tests for media download and processing."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_download_media_from_url(self, mock_client):
        """Test downloading media from URL."""
        from scripts.sample_integration.opencode_webhook_handler import download_media

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"fake image data"

        mock_context = AsyncMock()
        mock_context.get = AsyncMock(return_value=mock_response)
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()

        mock_client.return_value = mock_context

        message_data = {"media_url": "http://example.com/image.jpg", "type": "image"}

        files = await download_media(message_data)

        assert len(files) == 1
        assert Path(files[0]).exists()

        Path(files[0]).unlink()

    @pytest.mark.asyncio
    async def test_download_media_missing_url(self):
        """Test handling missing media URL."""
        from scripts.sample_integration.opencode_webhook_handler import download_media

        message_data = {"type": "image"}

        files = await download_media(message_data)

        assert files == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
