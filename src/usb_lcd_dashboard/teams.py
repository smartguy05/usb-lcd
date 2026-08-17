"""Microsoft Teams delegated authentication and background chat polling."""

from __future__ import annotations

import html
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from .config import config_home
from .messaging import MessageItem, MessageSnapshot

LOG = logging.getLogger(__name__)
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = ["Chat.Read", "User.Read"]
POLL_SECONDS = 60.0
REQUEST_TIMEOUT = 10.0


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"br", "p", "div", "li"}:
            self.parts.append(" ")


def plain_text(raw: str) -> str:
    parser = _PlainText()
    try:
        parser.feed(raw or "")
        text = " ".join("".join(parser.parts).split())
    except Exception:
        text = " ".join(html.unescape(raw or "").split())
    return text


def _date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _conversation_name(chat: dict[str, Any], me: str) -> str:
    if chat.get("topic"):
        return str(chat["topic"])
    names = []
    for member in chat.get("members") or []:
        identity = member.get("userId") or member.get("user", {}).get("id")
        if identity != me and member.get("displayName"):
            names.append(str(member["displayName"]))
    return ", ".join(names) or "Teams chat"


def parse_chats(chats: list[dict[str, Any]], me: str) -> MessageSnapshot:
    unread: list[MessageItem] = []
    for chat in chats:
        preview = chat.get("lastMessagePreview") or {}
        created = _date(preview.get("createdDateTime"))
        read = _date((chat.get("viewpoint") or {}).get("lastMessageReadDateTime"))
        sender = ((preview.get("from") or {}).get("user") or {})
        if not created or (read is not None and created <= read):
            continue
        if sender.get("id") == me:
            continue
        body = plain_text((preview.get("body") or {}).get("content") or "")
        if not body:
            body = str(preview.get("summary") or "New message")
        unread.append(
            MessageItem(
                provider="teams",
                conversation=_conversation_name(chat, me),
                sender=str(sender.get("displayName") or "Someone"),
                preview=body,
                created_at=created,
            )
        )
    unread.sort(key=lambda item: item.created_at, reverse=True)
    return MessageSnapshot(
        status="connected",
        latest=unread[0] if unread else None,
        unread_conversations=len(unread),
        updated_at=datetime.now(timezone.utc),
    )


class TeamsIntegration:
    """Owns auth, the polling thread, and the immutable snapshot it publishes."""

    def __init__(
        self,
        *,
        environ: dict[str, str] | None = None,
        app_factory: Callable[[], Any] | None = None,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        env = os.environ if environ is None else environ
        self.client_id = env.get("USB_LCD_TEAMS_CLIENT_ID", "").strip()
        self.tenant_id = env.get("USB_LCD_TEAMS_TENANT_ID", "").strip()
        self._app_factory = app_factory
        self._urlopen = urlopen
        self.poll_seconds = poll_seconds
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._auth_thread: threading.Thread | None = None
        self._app: Any = None
        self._me_id = ""
        self._enabled = False
        self._last_good: MessageSnapshot | None = None
        initial = "disconnected" if self.configured else "unconfigured"
        self._snapshot = MessageSnapshot(status=initial)
        self._device: dict[str, Any] = {}

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.tenant_id)

    def _make_app(self):
        if self._app is not None:
            return self._app
        if self._app_factory is not None:
            self._app = self._app_factory()
            return self._app
        try:
            import msal
            from msal_extensions import (
                FilePersistence,
                PersistedTokenCache,
                build_encrypted_persistence,
            )
        except ImportError as exc:  # pragma: no cover - installed package owns this
            raise RuntimeError("Microsoft authentication support is not installed") from exc

        cache_path = config_home() / "usb-lcd-dashboard/teams-token-cache.bin"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            persistence = build_encrypted_persistence(str(cache_path))
        except Exception as exc:
            LOG.warning("Encrypted Teams token cache unavailable; using a protected file: %s", exc)
            persistence = FilePersistence(str(cache_path))
        self._app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=PersistedTokenCache(persistence),
        )
        return self._app

    def start(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="usb-lcd-teams", daemon=True
            )
            self._thread.start()
        self._wake.set()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=REQUEST_TIMEOUT + 1)

    def snapshot(self) -> MessageSnapshot:
        with self._lock:
            return self._snapshot

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        with self._lock:
            device = dict(self._device)
        return {
            "configured": self.configured,
            "status": snap.status,
            "account": snap.account,
            "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
            "unread_conversations": snap.unread_conversations,
            "stale": snap.stale,
            "error": snap.error,
            "verification_uri": device.get("verification_uri")
            or device.get("verification_uri_complete"),
            "user_code": device.get("user_code"),
            "expires_at": device.get("expires_at"),
        }

    def connect(self) -> dict[str, Any]:
        if not self.configured:
            raise ValueError(
                "set USB_LCD_TEAMS_CLIENT_ID and USB_LCD_TEAMS_TENANT_ID, then restart"
            )
        if self._auth_thread is not None and self._auth_thread.is_alive():
            return self.status()
        app = self._make_app()
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(flow.get("error_description") or "could not start Teams login")
        expires = time.time() + int(flow.get("expires_in", 900))
        with self._lock:
            self._device = {**flow, "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat()}
            self._snapshot = MessageSnapshot(status="connecting")
        pending = self.status()
        self._auth_thread = threading.Thread(
            target=self._finish_connect, args=(app, flow), name="usb-lcd-teams-auth", daemon=True
        )
        self._auth_thread.start()
        return pending

    def _finish_connect(self, app, flow) -> None:
        try:
            result = app.acquire_token_by_device_flow(flow)
            if "access_token" not in result:
                raise RuntimeError(result.get("error_description") or "Teams login failed")
            account = result.get("id_token_claims", {}).get("preferred_username", "")
            with self._lock:
                self._device = {}
                self._snapshot = MessageSnapshot(status="connected", account=account)
            self._wake.set()
        except Exception as exc:
            with self._lock:
                self._device = {}
                self._snapshot = MessageSnapshot(status="error", error=str(exc))

    def disconnect(self) -> None:
        try:
            app = self._make_app() if self.configured else None
            if app is not None:
                for account in app.get_accounts():
                    app.remove_account(account)
        finally:
            self._me_id = ""
            self._last_good = None
            with self._lock:
                self._device = {}
                self._snapshot = MessageSnapshot(
                    status="disconnected" if self.configured else "unconfigured"
                )

    def _token(self) -> tuple[str, str]:
        app = self._make_app()
        accounts = app.get_accounts()
        if not accounts:
            return "", ""
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) or {}
        return str(result.get("access_token") or ""), str(
            accounts[0].get("username") or ""
        )

    def _json(self, url: str, token: str) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "graph.microsoft.com":
            raise RuntimeError("Microsoft Graph returned an unsafe pagination URL")
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )
        with self._urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read())

    def poll_once(self) -> MessageSnapshot:
        token, account = self._token()
        if not token:
            snapshot = MessageSnapshot(status="disconnected")
            with self._lock:
                self._snapshot = snapshot
            return snapshot
        if not self._me_id:
            me = self._json(f"{GRAPH_ROOT}/me?$select=id", token)
            self._me_id = str(me.get("id") or "")
        url = (
            f"{GRAPH_ROOT}/me/chats?"
            "$expand=lastMessagePreview,members&$top=50"
        )
        chats: list[dict[str, Any]] = []
        while url:
            page = self._json(url, token)
            chats.extend(page.get("value") or [])
            url = str(page.get("@odata.nextLink") or "")
        snapshot = parse_chats(chats, self._me_id)
        snapshot = MessageSnapshot(
            status=snapshot.status,
            latest=snapshot.latest,
            unread_conversations=snapshot.unread_conversations,
            updated_at=snapshot.updated_at,
            account=account,
        )
        self._last_good = snapshot
        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def _failure(self, exc: Exception) -> None:
        LOG.warning("Teams refresh failed: %s", exc)
        last = self._last_good
        failed = MessageSnapshot(
            status="error" if last is None else "connected",
            latest=last.latest if last else None,
            unread_conversations=last.unread_conversations if last else 0,
            updated_at=last.updated_at if last else None,
            account=last.account if last else "",
            error=str(exc),
            stale=last is not None,
        )
        with self._lock:
            self._snapshot = failed

    def _run(self) -> None:
        backoff = self.poll_seconds
        while not self._stop.is_set():
            self._wake.wait(backoff)
            self._wake.clear()
            if self._stop.is_set():
                break
            if not self._enabled or not self.configured:
                backoff = self.poll_seconds
                continue
            try:
                self.poll_once()
                backoff = self.poll_seconds
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    with self._lock:
                        self._snapshot = MessageSnapshot(
                            status="disconnected", error="Microsoft sign-in expired; reconnect in settings"
                        )
                    self._last_good = None
                else:
                    self._failure(exc)
                retry = exc.headers.get("Retry-After") if exc.headers else None
                backoff = min(300.0, float(retry) if retry and retry.isdigit() else backoff * 2)
            except Exception as exc:
                self._failure(exc)
                backoff = min(300.0, max(self.poll_seconds, backoff * 2))
