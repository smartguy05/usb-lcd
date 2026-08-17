"""Supported Discord bot integration for selected server channels."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import config_home
from .messaging import MessageItem, MessageSnapshot

LOG = logging.getLogger(__name__)
API_ROOT = "https://discord.com/api/v10"
POLL_SECONDS = 30.0
REQUEST_TIMEOUT = 10.0
MAX_PAGES = 5


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    source_buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _Blob()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    description = ctypes.c_wchar_p()
    args = (ctypes.byref(source), ctypes.byref(description), None, None, None, 0, ctypes.byref(target)) if decrypt else (
        ctypes.byref(source), "USB LCD Discord token", None, None, None, 0, ctypes.byref(target)
    )
    if not fn(*args):
        raise OSError(ctypes.get_last_error(), "Windows credential protection failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


class TokenStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_home() / "usb-lcd-dashboard/discord-token.bin"

    def load(self) -> str:
        try:
            data = self.path.read_bytes()
            if os.name == "nt":
                data = _dpapi(data, decrypt=True)
            return data.decode().strip()
        except FileNotFoundError:
            return ""

    def save(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = token.strip().encode()
        if os.name == "nt":
            data = _dpapi(data)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(data)
        if os.name != "nt":
            temp.chmod(0o600)
        os.replace(temp, self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def _date(raw: str | None) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def parse_message(raw: dict[str, Any], conversation: str) -> MessageItem:
    author = raw.get("author") or {}
    content = " ".join(str(raw.get("content") or "").split())
    if not content:
        attachments = raw.get("attachments") or []
        content = "Shared " + (str(attachments[0].get("filename") or "an attachment") if attachments else "a message")
    return MessageItem(
        provider="discord",
        conversation=conversation,
        sender=str(raw.get("member", {}).get("nick") or author.get("global_name") or author.get("username") or "Someone"),
        preview=content,
        created_at=_date(raw.get("timestamp")),
    )


class DiscordIntegration:
    def __init__(self, *, token_store: TokenStore | None = None, state_path: Path | None = None,
                 urlopen: Callable[..., Any] = urllib.request.urlopen, poll_seconds: float = POLL_SECONDS) -> None:
        self.token_store = token_store or TokenStore()
        self.state_path = state_path or config_home() / "usb-lcd-dashboard/discord-state.json"
        self._urlopen = urlopen
        self.poll_seconds = poll_seconds
        self.channel_ids: tuple[str, ...] = ()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = MessageSnapshot(status="unconfigured")
        self._bot: dict[str, Any] = {}
        self._channels: list[dict[str, str]] = []
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._state), encoding="utf-8")
        if os.name != "nt":
            temp.chmod(0o600)
        os.replace(temp, self.state_path)

    @property
    def configured(self) -> bool:
        return bool(self.token_store.load())

    def configure(self, channel_ids: tuple[str, ...]) -> None:
        self.channel_ids = channel_ids
        self._wake.set()

    def _json(self, path: str, *, token: str | None = None) -> Any:
        request = urllib.request.Request(API_ROOT + path, headers={
            "Authorization": "Bot " + (token or self.token_store.load()),
            "Accept": "application/json", "User-Agent": "USB-LCD-Dashboard/0.8.0",
        })
        with self._urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read())

    def save_token(self, token: str) -> dict[str, Any]:
        token = token.strip()
        if not token:
            raise ValueError("bot token is required")
        bot = self._json("/users/@me", token=token)
        if not bot.get("bot"):
            raise ValueError("Discord credential is not a bot token")
        self.token_store.save(token)
        self._bot = bot
        self.refresh_channels()
        self._snapshot = MessageSnapshot(status="connected", account=str(bot.get("username") or "Discord bot"))
        self._wake.set()
        return self.status()

    def disconnect(self) -> dict[str, Any]:
        self.token_store.clear()
        self._bot = {}
        self._channels = []
        self._snapshot = MessageSnapshot(status="unconfigured")
        return self.status()

    def refresh_channels(self) -> list[dict[str, str]]:
        guilds = self._json("/users/@me/guilds")
        channels: list[dict[str, str]] = []
        for guild in guilds:
            for channel in self._json(f"/guilds/{guild['id']}/channels"):
                if channel.get("type") in (0, 5):
                    channels.append({"id": str(channel["id"]), "name": str(channel.get("name") or channel["id"]),
                                     "guild_id": str(guild["id"]), "guild": str(guild.get("name") or guild["id"])})
        self._channels = sorted(channels, key=lambda value: (value["guild"].lower(), value["name"].lower()))
        return self._channels

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {"configured": self.configured, "status": snap.status, "bot": self._bot.get("username", ""),
                "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
                "new_messages": snap.unread_conversations, "stale": snap.stale, "error": snap.error,
                "channels": list(self._channels), "selected_channel_ids": list(self.channel_ids)}

    def snapshot(self) -> MessageSnapshot:
        with self._lock:
            return self._snapshot

    def clear(self) -> dict[str, Any]:
        for channel in self.channel_ids:
            entry = self._state.setdefault(channel, {})
            entry["count"] = 0
        self._save_state()
        current = self.snapshot()
        with self._lock:
            self._snapshot = MessageSnapshot(status=current.status, updated_at=current.updated_at,
                                             account=current.account, stale=current.stale, error=current.error)
        return self.status()

    def poll_once(self) -> MessageSnapshot:
        if not self.configured:
            result = MessageSnapshot(status="unconfigured")
            with self._lock: self._snapshot = result
            return result
        labels = {value["id"]: f"{value['guild']} · #{value['name']}" for value in self._channels}
        latest: MessageItem | None = None
        total = 0
        for channel in self.channel_ids:
            entry = self._state.setdefault(channel, {"cursor": "", "count": 0})
            if entry.get("latest") and int(entry.get("count", 0)):
                saved = parse_message(entry["latest"], str(entry.get("conversation") or labels.get(channel, "Discord channel")))
                if latest is None or saved.created_at > latest.created_at:
                    latest = saved
            query = "?limit=100" + ("&after=" + urllib.parse.quote(str(entry.get("cursor"))) if entry.get("cursor") else "")
            messages = self._json(f"/channels/{channel}/messages{query}")
            human = [m for m in messages if not (m.get("author") or {}).get("bot") and not m.get("webhook_id")]
            had_cursor = bool(entry.get("cursor"))
            if not had_cursor:
                entry["cursor"] = str(max((int(m["id"]) for m in messages), default=0) or "")
            elif messages:
                entry["cursor"] = str(max(int(m["id"]) for m in messages))
                entry["count"] = min(100, int(entry.get("count", 0)) + len(human))
            total += int(entry.get("count", 0))
            for raw in human if had_cursor else []:
                item = parse_message(raw, labels.get(channel, "Discord channel"))
                if latest is None or item.created_at > latest.created_at:
                    latest = item
                    entry["latest"] = raw
                    entry["conversation"] = labels.get(channel, "Discord channel")
        self._save_state()
        result = MessageSnapshot(status="connected", latest=latest if total else None,
                                 unread_conversations=min(total, 100), updated_at=datetime.now(timezone.utc),
                                 account=str(self._bot.get("username") or "Discord bot"))
        with self._lock: self._snapshot = result
        return result

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="usb-lcd-discord", daemon=True)
            self._thread.start()
        self._wake.set()

    def stop(self) -> None:
        self._stop.set(); self._wake.set()
        if self._thread is not None: self._thread.join(timeout=REQUEST_TIMEOUT + 1)

    def _run(self) -> None:
        wait = self.poll_seconds
        while not self._stop.is_set():
            self._wake.wait(wait); self._wake.clear()
            if self._stop.is_set(): break
            try:
                if self.configured and not self._channels: self.refresh_channels()
                self.poll_once(); wait = self.poll_seconds
            except urllib.error.HTTPError as exc:
                retry = exc.headers.get("Retry-After") if exc.headers else None
                wait = min(300.0, float(retry) if retry else max(self.poll_seconds, wait * 2))
                self._failure(f"Discord HTTP {exc.code}")
            except Exception as exc:
                wait = min(300.0, max(self.poll_seconds, wait * 2)); self._failure(str(exc))

    def _failure(self, error: str) -> None:
        old = self.snapshot()
        with self._lock:
            self._snapshot = MessageSnapshot(status="error" if old.updated_at is None else "connected", latest=old.latest,
                unread_conversations=old.unread_conversations, updated_at=old.updated_at, account=old.account,
                error=error, stale=old.updated_at is not None)
        LOG.warning("Discord refresh failed: %s", error)
