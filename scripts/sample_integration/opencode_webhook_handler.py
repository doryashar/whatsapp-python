#!/usr/bin/env python3
"""
OpenCode WhatsApp Webhook Handler

Receives WhatsApp webhook events and processes messages through OpenCode CLI.
Maintains per-chat sessions for conversation context.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import httpx
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.sample_integration.session_manager import SessionManager

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

session_manager: Optional[SessionManager] = None

WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://localhost:8080")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin123")
OPENCODE_TIMEOUT = int(os.getenv("OPENCODE_TIMEOUT", "120"))
SESSION_DB_PATH = os.getenv("SESSION_DB_PATH", "./data/sessions.db")
PROMPT_FILE = os.getenv("PROMPT_FILE", "PROMPT.md")


class WebhookEvent(BaseModel):
    type: str
    data: dict
    timestamp: int


class SessionInfo(BaseModel):
    chat_jid: str
    opencode_session_id: str
    created_at: str
    last_used_at: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global session_manager
    session_manager = SessionManager(SESSION_DB_PATH)
    await session_manager.init_db()
    logger.info("Webhook handler started")

    yield

    if session_manager:
        await session_manager.close()
    logger.info("Webhook handler stopped")


app = FastAPI(title="OpenCode WhatsApp Webhook Handler", lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "opencode-webhook"}


@app.post("/webhook")
async def handle_webhook(event: WebhookEvent, background_tasks: BackgroundTasks):
    """
    Handle incoming webhook events from WhatsApp API.
    Processes messages asynchronously in the background.
    """
    if event.type == "message":
        background_tasks.add_task(process_message, event.data)
        return {"status": "accepted"}

    logger.debug(f"Ignoring event type: {event.type}")
    return {"status": "ignored"}


async def process_message(message_data: dict):
    """
    Process an incoming WhatsApp message.

    Args:
        message_data: Message data from WhatsApp webhook
    """
    if not session_manager:
        logger.error("Session manager not initialized")
        return

    try:
        chat_jid = message_data.get("chat_jid")
        if not chat_jid:
            logger.warning("Message missing chat_jid")
            return

        if message_data.get("from_me"):
            logger.debug(f"Ignoring message from self: {chat_jid}")
            return

        message_text = message_data.get("text", "")
        message_type = message_data.get("type", "text")
        message_id = message_data.get("id")

        logger.info(f"Processing {message_type} message from {chat_jid}")

        media_files = []
        if message_type in ["image", "video", "audio", "document"]:
            media_files = await download_media(message_data)

        session_id = await session_manager.get_session(chat_jid)

        if session_id:
            logger.debug(f"Continuing session {session_id} for {chat_jid}")
            response = await run_opencode(
                message=message_text, session_id=session_id, files=media_files
            )
        else:
            logger.debug(f"Creating new session for {chat_jid}")
            response = await run_opencode(
                message=message_text, prompt_file=PROMPT_FILE, files=media_files
            )

            if response.get("session_id"):
                await session_manager.create_session(chat_jid, response["session_id"])

        if response.get("text"):
            await send_whatsapp_message(chat_jid, response["text"])
        else:
            logger.warning("No response text from opencode")

        for media_file in media_files:
            try:
                Path(media_file).unlink()
            except Exception as e:
                logger.error(f"Failed to cleanup media file: {e}")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


async def download_media(message_data: dict) -> list[str]:
    """
    Download media from WhatsApp message.

    Args:
        message_data: Message data containing media info

    Returns:
        List of downloaded file paths
    """
    media_files = []

    try:
        media_url = message_data.get("media_url")
        media_type = message_data.get("type", "image")

        if not media_url:
            logger.warning("Media message has no media_url")
            return media_files

        if media_url.startswith("http"):
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    media_url, headers={"X-API-Key": WHATSAPP_API_KEY}, timeout=30.0
                )

                if response.status_code == 200:
                    ext = (
                        media_type.replace("image", "jpg")
                        .replace("video", "mp4")
                        .replace("audio", "mp3")
                    )
                    with tempfile.NamedTemporaryFile(
                        mode="wb", suffix=f".{ext}", delete=False
                    ) as f:
                        f.write(response.content)
                        media_files.append(f.name)
                        logger.info(f"Downloaded media to {f.name}")
                else:
                    logger.error(f"Failed to download media: {response.status_code}")
        else:
            if Path(media_url).exists():
                media_files.append(media_url)

    except Exception as e:
        logger.error(f"Error downloading media: {e}", exc_info=True)

    return media_files


async def run_opencode(
    message: str,
    session_id: Optional[str] = None,
    prompt_file: Optional[str] = None,
    files: Optional[list[str]] = None,
) -> dict:
    """
    Run opencode CLI command.

    Args:
        message: Message to send to opencode
        session_id: Existing session ID to continue
        prompt_file: Prompt file for new session
        files: List of file paths to attach

    Returns:
        Dictionary with 'text' and 'session_id' keys
    """
    if files is None:
        files = []

    cmd = ["opencode", "run", "--format", "json"]

    if session_id:
        cmd.extend(["--session", session_id])
        logger.debug(f"Using session: {session_id}")
    elif prompt_file and Path(prompt_file).exists():
        prompt_content = Path(prompt_file).read_text()
        cmd.extend(["--prompt", prompt_content])
        logger.debug(f"Using prompt from {prompt_file}")

    for file_path in files:
        if Path(file_path).exists():
            cmd.extend(["-f", file_path])
            logger.debug(f"Attaching file: {file_path}")

    if message.strip():
        cmd.extend(["--", message])

    logger.info(f"Running opencode: {' '.join(cmd[:5])}...")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path(__file__).parent.parent),
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=OPENCODE_TIMEOUT
        )

        if process.returncode != 0:
            logger.error(f"OpenCode failed: {stderr.decode()}")
            return {
                "text": "Sorry, I encountered an error processing your request.",
                "session_id": None,
            }

        response_text = stdout.decode().strip()

        result = parse_opencode_response(response_text)
        logger.info(f"OpenCode response length: {len(result.get('text', ''))}")

        return result

    except asyncio.TimeoutError:
        logger.error(f"OpenCode timeout after {OPENCODE_TIMEOUT}s")
        return {"text": "Sorry, the request timed out.", "session_id": None}
    except Exception as e:
        logger.error(f"Error running opencode: {e}", exc_info=True)
        return {"text": "Sorry, an error occurred.", "session_id": None}


def parse_opencode_response(response_text: str) -> dict:
    """
    Parse opencode JSON response.

    Args:
        response_text: Raw response from opencode

    Returns:
        Dictionary with 'text' and 'session_id' keys
    """
    try:
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                if data.get("type") == "response":
                    text = data.get("data", {}).get("content", "")
                    session_id = data.get("data", {}).get("session_id")

                    return {"text": text, "session_id": session_id}
            except json.JSONDecodeError:
                continue

        logger.warning("Could not parse opencode response as JSON")
        return {"text": response_text, "session_id": None}

    except Exception as e:
        logger.error(f"Error parsing response: {e}")
        return {"text": response_text, "session_id": None}


async def send_whatsapp_message(chat_jid: str, text: str):
    """
    Send a message back via WhatsApp API.

    Args:
        chat_jid: WhatsApp chat JID
        text: Message text to send
    """
    if not text or not text.strip():
        logger.warning("Attempted to send empty message")
        return

    max_length = 4000
    if len(text) > max_length:
        text = text[: max_length - 50] + "\n\n[Message truncated due to length]"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{WHATSAPP_API_URL}/api/send",
                json={"to": chat_jid.split("@")[0], "text": text},
                headers={"X-API-Key": WHATSAPP_API_KEY},
                timeout=30.0,
            )

            if response.status_code == 200:
                logger.info(f"Message sent to {chat_jid}")
            else:
                logger.error(
                    f"Failed to send message: {response.status_code} - {response.text}"
                )

    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {e}", exc_info=True)


@app.get("/sessions")
async def list_sessions(x_api_key: str = Header(None)):
    """List all active sessions (admin endpoint)."""
    if not session_manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    sessions = await session_manager.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.delete("/sessions/{chat_jid}")
async def delete_session(chat_jid: str, x_api_key: str = Header(None)):
    """Delete a session (admin endpoint)."""
    if not session_manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    deleted = await session_manager.delete_session(chat_jid)

    if deleted:
        return {"status": "deleted", "chat_jid": chat_jid}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@app.post("/cleanup")
async def cleanup_sessions(x_api_key: str = Header(None), days_old: int = 30):
    """Cleanup old sessions (admin endpoint)."""
    if not session_manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    deleted_count = await session_manager.cleanup_old_sessions(days_old)
    return {"deleted_count": deleted_count}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBHOOK_PORT", "5556"))
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")

    logger.info(f"Starting webhook handler on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
