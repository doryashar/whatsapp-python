import asyncio
from typing import Any, Callable, Optional
from unittest.mock import MagicMock


class MockBridge:
    """Mock bridge that simulates BaileysBridge for unit testing."""

    def __init__(self):
        self._running = True
        self._event_handlers: list[Callable] = []
        self.call_history: list[tuple[str, dict | None]] = []
        self.call_results: dict[str, Any] = {}
        self.call_errors: dict[str, Exception] = {}
        self.events: list[tuple[str, dict]] = []
        self.start_called = False
        self.stop_called = False

    def on_event(self, handler: Callable) -> None:
        self._event_handlers.append(handler)

    async def start(self) -> None:
        self.start_called = True
        self._running = True

    async def stop(self) -> None:
        self.stop_called = True
        self._running = False

    def is_alive(self) -> bool:
        return self._running

    async def _call(self, method: str, params: dict | None = None) -> Any:
        self.call_history.append((method, params))
        if method in self.call_errors:
            raise self.call_errors[method]
        return self.call_results.get(method, {"status": "ok"})

    async def login(self) -> dict:
        return await self._call("login")

    async def logout(self) -> dict:
        return await self._call("logout")

    async def send_message(
        self, to: str, text: str, media_url: str | None = None, **kwargs
    ) -> dict:
        return await self._call(
            "send_message", {"to": to, "text": text, "media_url": media_url}
        )

    async def send_reaction(
        self, chat: str, message_id: str, emoji: str, from_me: bool = False
    ) -> dict:
        return await self._call(
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
        return await self._call(
            "send_poll",
            {
                "to": to,
                "name": name,
                "values": values,
                "selectable_count": selectable_count,
            },
        )

    async def send_typing(self, to: str) -> dict:
        return await self._call("send_typing", {"to": to})

    async def auth_exists(self) -> dict:
        return await self._call("auth_exists")

    async def auth_age(self) -> dict:
        return await self._call("auth_age")

    async def self_id(self) -> dict:
        return await self._call("self_id")

    async def get_status(self) -> dict:
        return await self._call("get_status")

    async def get_contacts(self) -> dict:
        return await self._call("get_contacts")

    async def get_chats_with_messages(self, limit_per_chat: int = 50) -> dict:
        return await self._call("get_chats_with_messages", {"limit": limit_per_chat})

    async def fetch_chat_history(
        self, limit_per_chat: int = 50, max_chats: int = 100
    ) -> dict:
        return await self._call(
            "fetch_chat_history",
            {"limit_per_chat": limit_per_chat, "max_chats": max_chats},
        )

    async def get_profile_picture(self, jid: str) -> dict:
        return await self._call("get_profile_picture", {"jid": jid})

    async def delete_message(
        self, to: str, message_id: str, from_me: bool = False
    ) -> dict:
        return await self._call(
            "delete_message", {"to": to, "message_id": message_id, "from_me": from_me}
        )

    async def mark_read(self, to: str, message_ids: list[str]) -> dict:
        return await self._call("mark_read", {"to": to, "message_ids": message_ids})

    async def group_create(
        self, subject: str, participants: list[str], description: str | None = None
    ) -> dict:
        return await self._call(
            "group_create",
            {
                "subject": subject,
                "participants": participants,
                "description": description,
            },
        )

    async def group_update_subject(self, group_jid: str, subject: str) -> dict:
        return await self._call(
            "group_update_subject", {"group_jid": group_jid, "subject": subject}
        )

    async def group_update_description(self, group_jid: str, description: str) -> dict:
        return await self._call(
            "group_update_description",
            {"group_jid": group_jid, "description": description},
        )

    async def group_update_picture(self, group_jid: str, image_url: str) -> dict:
        return await self._call(
            "group_update_picture", {"group_jid": group_jid, "image_url": image_url}
        )

    async def group_get_info(self, group_jid: str) -> dict:
        return await self._call("group_get_info", {"group_jid": group_jid})

    async def group_get_all(self, get_participants: bool = False) -> dict:
        return await self._call("group_get_all", {"get_participants": get_participants})

    async def group_get_participants(self, group_jid: str) -> dict:
        return await self._call("group_get_participants", {"group_jid": group_jid})

    async def group_get_invite_code(self, group_jid: str) -> dict:
        return await self._call("group_get_invite_code", {"group_jid": group_jid})

    async def group_revoke_invite(self, group_jid: str) -> dict:
        return await self._call("group_revoke_invite", {"group_jid": group_jid})

    async def group_accept_invite(self, invite_code: str) -> dict:
        return await self._call("group_accept_invite", {"invite_code": invite_code})

    async def group_get_invite_info(self, invite_code: str) -> dict:
        return await self._call("group_get_invite_info", {"invite_code": invite_code})

    async def group_update_participant(
        self, group_jid: str, action: str, participants: list[str]
    ) -> dict:
        return await self._call(
            "group_update_participant",
            {"group_jid": group_jid, "action": action, "participants": participants},
        )

    async def group_update_setting(self, group_jid: str, action: str) -> dict:
        return await self._call(
            "group_update_setting", {"group_jid": group_jid, "action": action}
        )

    async def group_toggle_ephemeral(self, group_jid: str, expiration: int) -> dict:
        return await self._call(
            "group_toggle_ephemeral", {"group_jid": group_jid, "expiration": expiration}
        )

    async def group_leave(self, group_jid: str) -> dict:
        return await self._call("group_leave", {"group_jid": group_jid})

    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
    ) -> dict:
        return await self._call(
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
        return await self._call("send_contact", {"to": to, "contacts": contacts})

    async def archive_chat(self, chat_jid: str, archive: bool = True) -> dict:
        return await self._call(
            "archive_chat", {"chat_jid": chat_jid, "archive": archive}
        )

    async def block_user(self, jid: str, block: bool = True) -> dict:
        return await self._call("block_user", {"jid": jid, "block": block})

    async def edit_message(
        self, to: str, message_id: str, text: str, from_me: bool = True
    ) -> dict:
        return await self._call(
            "edit_message",
            {"to": to, "message_id": message_id, "text": text, "from_me": from_me},
        )

    async def check_whatsapp(self, numbers: list[str]) -> dict:
        return await self._call("check_whatsapp", {"numbers": numbers})

    async def update_profile_name(self, name: str) -> dict:
        return await self._call("update_profile_name", {"name": name})

    async def update_profile_status(self, status: str) -> dict:
        return await self._call("update_profile_status", {"status": status})

    async def update_profile_picture(self, image_url: str) -> dict:
        return await self._call("update_profile_picture", {"image_url": image_url})

    async def remove_profile_picture(self) -> dict:
        return await self._call("remove_profile_picture")

    async def get_profile(self, jid: str | None = None) -> dict:
        return await self._call("get_profile", {"jid": jid})

    async def send_sticker(
        self, to: str, sticker: str, gif_playback: bool = False
    ) -> dict:
        return await self._call(
            "send_sticker", {"to": to, "sticker": sticker, "gif_playback": gif_playback}
        )

    async def send_buttons(
        self,
        to: str,
        title: str,
        description: str,
        buttons: list[dict],
        footer: str | None = None,
        thumbnail_url: str | None = None,
    ) -> dict:
        return await self._call(
            "send_buttons",
            {
                "to": to,
                "title": title,
                "description": description,
                "buttons": buttons,
                "footer": footer,
                "thumbnail_url": thumbnail_url,
            },
        )

    async def send_list(
        self,
        to: str,
        title: str,
        description: str,
        button_text: str,
        sections: list[dict],
        footer: str | None = None,
    ) -> dict:
        return await self._call(
            "send_list",
            {
                "to": to,
                "title": title,
                "description": description,
                "button_text": button_text,
                "sections": sections,
                "footer": footer,
            },
        )

    async def send_status(
        self,
        type: str,
        content: str,
        caption: str | None = None,
        background_color: str | None = None,
        font: int | None = None,
        status_jid_list: list[str] | None = None,
        all_contacts: bool = False,
    ) -> dict:
        return await self._call(
            "send_status",
            {
                "type": type,
                "content": content,
                "caption": caption,
                "background_color": background_color,
                "font": font,
                "status_jid_list": status_jid_list,
                "all_contacts": all_contacts,
            },
        )

    async def fetch_privacy_settings(self) -> dict:
        return await self._call("fetch_privacy_settings")

    async def update_privacy_settings(
        self,
        readreceipts: str | None = None,
        profile: str | None = None,
        status: str | None = None,
        online: str | None = None,
        last: str | None = None,
        groupadd: str | None = None,
    ) -> dict:
        return await self._call(
            "update_privacy_settings",
            {
                "readreceipts": readreceipts,
                "profile": profile,
                "status": status,
                "online": online,
                "last": last,
                "groupadd": groupadd,
            },
        )

    async def get_settings(self) -> dict:
        return await self._call("get_settings")

    async def update_settings(
        self,
        reject_call: bool | None = None,
        msg_call: str | None = None,
        groups_ignore: bool | None = None,
        always_online: bool | None = None,
        read_messages: bool | None = None,
        read_status: bool | None = None,
        sync_full_history: bool | None = None,
    ) -> dict:
        return await self._call(
            "update_settings",
            {
                "reject_call": reject_call,
                "msg_call": msg_call,
                "groups_ignore": groups_ignore,
                "always_online": always_online,
                "read_messages": read_messages,
                "read_status": read_status,
                "sync_full_history": sync_full_history,
            },
        )

    def simulate_event(self, method: str, params: dict | None = None):
        """Simulate a bridge event by calling all registered handlers."""
        self.events.append((method, params or {}))
        for handler in self._event_handlers:
            handler(method, params or {}, None)

    def set_result(self, method: str, result: Any) -> "MockBridge":
        self.call_results[method] = result
        return self

    def set_error(self, method: str, error: Exception) -> "MockBridge":
        self.call_errors[method] = error
        return self
