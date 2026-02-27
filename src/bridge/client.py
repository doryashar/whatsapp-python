import asyncio
import os
from typing import Any, Callable, Optional
from pathlib import Path

from .protocol import encode_request, decode_response, JsonRpcEvent, JsonRpcResponse
from ..config import settings


class BridgeError(Exception):
    pass


class BaileysBridge:
    def __init__(
        self,
        bridge_path: Optional[Path] = None,
        auth_dir: Optional[Path] = None,
        auto_login: bool = False,
    ):
        self.bridge_path = bridge_path or settings.bridge_path
        self.auth_dir = auth_dir or settings.auth_dir
        self.auto_login = auto_login

        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: list[Callable[[str, dict], None]] = []
        self._running = False

    def on_event(self, handler: Callable[[str, dict], None]) -> None:
        self._event_handlers.append(handler)

    async def start(self) -> None:
        if self._running:
            return

        env = os.environ.copy()
        env["WHATSAPP_AUTH_DIR"] = str(self.auth_dir)
        if self.auto_login:
            env["AUTO_LOGIN"] = "true"

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

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process:
            try:
                self._process.stdin.close()
                await self._process.wait()
            except Exception:
                pass

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

                msg = decode_response(data)

                if isinstance(msg, JsonRpcResponse):
                    if msg.id is not None and msg.id in self._pending:
                        future = self._pending.pop(msg.id)
                        if msg.error:
                            future.set_exception(
                                BridgeError(msg.error.get("message", "Unknown error"))
                            )
                        else:
                            future.set_result(msg.result)

                elif isinstance(msg, JsonRpcEvent):
                    await self._handle_event(msg.method, msg.params)

            except asyncio.CancelledError:
                break
            except Exception as e:
                pass

    async def _stderr_loop(self) -> None:
        if not self._process or not self._process.stderr:
            return

        reader = self._process.stderr
        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
            except Exception:
                break

    async def _handle_event(self, method: str, params: dict) -> None:
        for handler in self._event_handlers:
            try:
                result = handler(method, params)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def call(self, method: str, params: Optional[dict] = None) -> Any:
        if not self._process or not self._process.stdin:
            raise BridgeError("Bridge not started")

        self._request_id += 1
        request_id = self._request_id

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        data = encode_request(method, params, request_id) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

        return await future

    async def login(self) -> dict:
        return await self.call("login")

    async def logout(self) -> dict:
        return await self.call("logout")

    async def send_message(
        self, to: str, text: str, media_url: Optional[str] = None
    ) -> dict:
        return await self.call(
            "send_message", {"to": to, "text": text, "media_url": media_url}
        )

    async def send_reaction(self, chat: str, message_id: str, emoji: str) -> dict:
        return await self.call(
            "send_reaction", {"chat": chat, "message_id": message_id, "emoji": emoji}
        )

    async def get_status(self) -> dict:
        return await self.call("get_status")


bridge = BaileysBridge()
