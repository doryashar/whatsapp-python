import asyncio
import os
from typing import Any, Callable, Optional, Awaitable, Union, cast
from pathlib import Path

from .protocol import encode_request, decode_response, JsonRpcEvent, JsonRpcResponse
from ..config import settings
from ..telemetry import get_logger

logger = get_logger("whatsapp.bridge")


class BridgeError(Exception):
    pass


class BaileysBridge:
    def __init__(
        self,
        bridge_path: Optional[Path] = None,
        auth_dir: Optional[Path] = None,
        auto_login: bool = False,
        tenant_id: Optional[str] = None,
    ):
        self.bridge_path = bridge_path or settings.bridge_path
        self.auth_dir = auth_dir or settings.auth_dir
        self.auto_login = auto_login
        self.tenant_id = tenant_id

        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: list[Callable[[str, dict, Optional[str]], None]] = []
        self._running = False
        logger.debug(
            f"BaileysBridge created: auth_dir={self.auth_dir}, tenant={tenant_id[:16] if tenant_id else 'none'}..."
        )

    def on_event(self, handler: Callable[[str, dict, Optional[str]], None]) -> None:
        logger.debug("Registering bridge event handler")
        self._event_handlers.append(handler)

    async def start(self) -> None:
        if self._running:
            logger.debug("Bridge already running")
            return

        env = os.environ.copy()
        env["WHATSAPP_AUTH_DIR"] = str(self.auth_dir)
        if self.auto_login:
            env["AUTO_LOGIN"] = "true"

        logger.info(f"Starting bridge: node {self.bridge_path}")
        self._process = await asyncio.create_subprocess_exec(
            "node",
            str(self.bridge_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._running = True
        self._reader_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._stderr_loop())
        logger.info(f"Bridge started (pid={self._process.pid})")

    async def stop(self) -> None:
        if not self._running:
            logger.debug("Bridge not running, nothing to stop")
            return

        logger.info("Stopping bridge")
        self._running = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                await self._process.wait()
                logger.info(f"Bridge stopped (pid={self._process.pid})")
            except Exception as e:
                logger.debug(f"Error stopping bridge: {e}")

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return

        reader = self._process.stdout
        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break

                data = line.decode("utf-8").strip()
                if not data:
                    continue

                logger.debug(
                    f"Bridge <- {data[:200]}{'...' if len(data) > 200 else ''}"
                )
                msg = decode_response(data)

                if isinstance(msg, JsonRpcResponse):
                    if msg.id is not None and msg.id in self._pending:
                        future = self._pending.pop(msg.id)
                        if msg.error:
                            logger.debug(f"Bridge response error: {msg.error}")
                            future.set_exception(
                                BridgeError(msg.error.get("message", "Unknown error"))
                            )
                        else:
                            logger.debug(f"Bridge response success: id={msg.id}")
                            future.set_result(msg.result)

                elif isinstance(msg, JsonRpcEvent):
                    logger.debug(f"Bridge event: {msg.method}")
                    await self._handle_event(msg.method, msg.params)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Bridge read error: {e}")

    async def _stderr_loop(self) -> None:
        if not self._process or not self._process.stderr:
            return

        reader = self._process.stderr
        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
                logger.debug(f"Bridge stderr: {line.decode('utf-8').strip()}")
            except Exception:
                break

    async def _handle_event(self, method: str, params: dict) -> None:
        for handler in self._event_handlers:
            try:
                result = handler(method, params, self.tenant_id)
                if asyncio.iscoroutine(result):
                    await result  # type: ignore[arg-type]
            except Exception as e:
                logger.debug(f"Event handler error: {e}")

    async def call(self, method: str, params: Optional[dict] = None) -> Any:
        if not self._process or not self._process.stdin:
            raise BridgeError("Bridge not started")

        self._request_id += 1
        request_id = self._request_id

        logger.debug(f"Bridge call: {method}(id={request_id}, params={params})")
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        data = encode_request(method, params, request_id) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(
                future, timeout=settings.bridge_timeout_seconds
            )
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise BridgeError(
                f"Bridge call timed out after {settings.bridge_timeout_seconds}s: {method}"
            )

    async def login(self) -> dict:
        logger.info("Bridge login requested")
        return await self.call("login")

    async def logout(self) -> dict:
        logger.info("Bridge logout requested")
        return await self.call("logout")

    async def send_message(
        self, to: str, text: str, media_url: Optional[str] = None
    ) -> dict:
        logger.info(f"Bridge send_message: to={to}")
        return await self.call(
            "send_message", {"to": to, "text": text, "media_url": media_url}
        )

    async def send_reaction(
        self, chat: str, message_id: str, emoji: str, from_me: bool = False
    ) -> dict:
        logger.debug(f"Bridge send_reaction: chat={chat}, emoji={emoji}")
        return await self.call(
            "send_reaction",
            {
                "chat": chat,
                "message_id": message_id,
                "emoji": emoji,
                "from_me": from_me,
            },
        )

    async def send_poll(
        self, to: str, name: str, values: list[str], selectable_count: int = 1
    ) -> dict:
        logger.info(f"Bridge send_poll: to={to}, name={name}")
        return await self.call(
            "send_poll",
            {
                "to": to,
                "poll": {
                    "name": name,
                    "values": values,
                    "selectableCount": selectable_count,
                },
            },
        )

    async def send_typing(self, to: str) -> dict:
        logger.debug(f"Bridge send_typing: to={to}")
        return await self.call("send_typing", {"to": to})

    async def auth_exists(self) -> dict:
        return await self.call("auth_exists")

    async def auth_age(self) -> dict:
        return await self.call("auth_age")

    async def self_id(self) -> dict:
        return await self.call("self_id")

    async def get_status(self) -> dict:
        return await self.call("get_status")

    async def get_contacts(self) -> dict:
        logger.info("Bridge get_contacts requested")
        return await self.call("get_contacts")

    async def get_profile_picture(self, jid: str) -> dict:
        logger.debug(f"Bridge get_profile_picture: jid={jid}")
        return await self.call("get_profile_picture", {"jid": jid})

    async def delete_message(
        self, to: str, message_id: str, from_me: bool = False
    ) -> dict:
        logger.info(f"Bridge delete_message: to={to}, message_id={message_id}")
        return await self.call(
            "delete_message",
            {"to": to, "message_id": message_id, "from_me": from_me},
        )

    async def mark_read(self, to: str, message_ids: list[str]) -> dict:
        logger.debug(f"Bridge mark_read: to={to}, count={len(message_ids)}")
        return await self.call(
            "mark_read",
            {"to": to, "message_ids": message_ids},
        )

    # Group Management Methods

    async def group_create(
        self, subject: str, participants: list[str], description: str | None = None
    ) -> dict:
        logger.info(
            f"Bridge group_create: subject={subject}, participants={len(participants)}"
        )
        return await self.call(
            "group_create",
            {
                "subject": subject,
                "participants": participants,
                "description": description,
            },
        )

    async def group_update_subject(self, group_jid: str, subject: str) -> dict:
        logger.debug(
            f"Bridge group_update_subject: group={group_jid}, subject={subject}"
        )
        return await self.call(
            "group_update_subject",
            {"group_jid": group_jid, "subject": subject},
        )

    async def group_update_description(self, group_jid: str, description: str) -> dict:
        logger.debug(f"Bridge group_update_description: group={group_jid}")
        return await self.call(
            "group_update_description",
            {"group_jid": group_jid, "description": description},
        )

    async def group_update_picture(self, group_jid: str, image_url: str) -> dict:
        logger.debug(f"Bridge group_update_picture: group={group_jid}")
        return await self.call(
            "group_update_picture",
            {"group_jid": group_jid, "image_url": image_url},
        )

    async def group_get_info(self, group_jid: str) -> dict:
        logger.debug(f"Bridge group_get_info: group={group_jid}")
        return await self.call("group_get_info", {"group_jid": group_jid})

    async def group_get_all(self, get_participants: bool = False) -> dict:
        logger.info("Bridge group_get_all requested")
        return await self.call("group_get_all", {"get_participants": get_participants})

    async def group_get_participants(self, group_jid: str) -> dict:
        logger.debug(f"Bridge group_get_participants: group={group_jid}")
        return await self.call("group_get_participants", {"group_jid": group_jid})

    async def group_get_invite_code(self, group_jid: str) -> dict:
        logger.debug(f"Bridge group_get_invite_code: group={group_jid}")
        return await self.call("group_get_invite_code", {"group_jid": group_jid})

    async def group_revoke_invite(self, group_jid: str) -> dict:
        logger.debug(f"Bridge group_revoke_invite: group={group_jid}")
        return await self.call("group_revoke_invite", {"group_jid": group_jid})

    async def group_accept_invite(self, invite_code: str) -> dict:
        logger.info(f"Bridge group_accept_invite: code={invite_code[:8]}...")
        return await self.call("group_accept_invite", {"invite_code": invite_code})

    async def group_get_invite_info(self, invite_code: str) -> dict:
        logger.debug(f"Bridge group_get_invite_info: code={invite_code[:8]}...")
        return await self.call("group_get_invite_info", {"invite_code": invite_code})

    async def group_update_participant(
        self, group_jid: str, action: str, participants: list[str]
    ) -> dict:
        logger.info(
            f"Bridge group_update_participant: group={group_jid}, action={action}, count={len(participants)}"
        )
        return await self.call(
            "group_update_participant",
            {"group_jid": group_jid, "action": action, "participants": participants},
        )

    async def group_update_setting(self, group_jid: str, action: str) -> dict:
        logger.debug(f"Bridge group_update_setting: group={group_jid}, action={action}")
        return await self.call(
            "group_update_setting",
            {"group_jid": group_jid, "action": action},
        )

    async def group_toggle_ephemeral(self, group_jid: str, expiration: int) -> dict:
        logger.debug(
            f"Bridge group_toggle_ephemeral: group={group_jid}, expiration={expiration}"
        )
        return await self.call(
            "group_toggle_ephemeral",
            {"group_jid": group_jid, "expiration": expiration},
        )

    async def group_leave(self, group_jid: str) -> dict:
        logger.info(f"Bridge group_leave: group={group_jid}")
        return await self.call("group_leave", {"group_jid": group_jid})

    # Advanced Messaging

    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
    ) -> dict:
        logger.info(f"Bridge send_location: to={to}, lat={latitude}, lng={longitude}")
        return await self.call(
            "send_location",
            {
                "to": to,
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
            },
        )

    async def send_contact(self, to: str, contacts: list[dict]) -> dict:
        logger.info(f"Bridge send_contact: to={to}, count={len(contacts)}")
        return await self.call("send_contact", {"to": to, "contacts": contacts})

    # Chat Operations

    async def archive_chat(self, chat_jid: str, archive: bool = True) -> dict:
        logger.info(f"Bridge archive_chat: chat={chat_jid}, archive={archive}")
        return await self.call(
            "archive_chat", {"chat_jid": chat_jid, "archive": archive}
        )

    async def block_user(self, jid: str, block: bool = True) -> dict:
        logger.info(f"Bridge block_user: jid={jid}, block={block}")
        return await self.call("block_user", {"jid": jid, "block": block})

    async def edit_message(
        self, to: str, message_id: str, text: str, from_me: bool = True
    ) -> dict:
        logger.info(f"Bridge edit_message: to={to}, message_id={message_id}")
        return await self.call(
            "edit_message",
            {"to": to, "message_id": message_id, "text": text, "from_me": from_me},
        )

    async def check_whatsapp(self, numbers: list[str]) -> dict:
        logger.info(f"Bridge check_whatsapp: count={len(numbers)}")
        return await self.call("check_whatsapp", {"numbers": numbers})

    # Profile Operations

    async def update_profile_name(self, name: str) -> dict:
        logger.info(f"Bridge update_profile_name: name={name}")
        return await self.call("update_profile_name", {"name": name})

    async def update_profile_status(self, status: str) -> dict:
        logger.info(f"Bridge update_profile_status: status={status[:30]}...")
        return await self.call("update_profile_status", {"status": status})

    async def update_profile_picture(self, image_url: str) -> dict:
        logger.info("Bridge update_profile_picture")
        return await self.call("update_profile_picture", {"image_url": image_url})

    async def remove_profile_picture(self) -> dict:
        logger.info("Bridge remove_profile_picture")
        return await self.call("remove_profile_picture")

    async def get_profile(self, jid: str | None = None) -> dict:
        logger.debug(f"Bridge get_profile: jid={jid}")
        return await self.call("get_profile", {"jid": jid})

    def is_alive(self) -> bool:
        if not self._process or not self._running:
            return False
        return self._process.returncode is None
