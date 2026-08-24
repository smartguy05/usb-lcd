"""Claude subscription limit snapshots for the LCD limits widget.

Claude Code supplies the shared five-hour and seven-day windows to its status
line.  The same windows, plus model-scoped limits, are periodically refreshed
from the OAuth usage endpoint that backs Claude's own usage UI.  Only normalized
percentages and timestamps are persisted; credentials and raw responses are not.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import config_home

LOG = logging.getLogger(__name__)
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REFRESH_SECONDS = 15 * 60
RATE_LIMIT_BACKOFF_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class LimitWindow:
    used_percentage: float
    resets_at: datetime
    updated_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class ClaudeLimitsSnapshot:
    five_hour: LimitWindow | None = None
    seven_day: LimitWindow | None = None
    fable: LimitWindow | None = None
    status: str = "waiting"
    error: str = ""


def _percent(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(100.0, number))


def _timestamp(value: Any) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc)
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def parse_window(data: Any, source: str, now: datetime) -> LimitWindow | None:
    if not isinstance(data, dict):
        return None
    used = _percent(data.get("used_percentage", data.get("utilization")))
    resets = _timestamp(data.get("resets_at"))
    if used is None or resets is None:
        return None
    return LimitWindow(used, resets, now, source)


def _scoped_entries(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    scoped = payload.get("weekly_scoped")
    if isinstance(scoped, list):
        yield from (entry for entry in scoped if isinstance(entry, dict))
    elif isinstance(scoped, dict):
        yield from (entry for entry in scoped.values() if isinstance(entry, dict))


def parse_fable(payload: Any, now: datetime) -> LimitWindow | None:
    if not isinstance(payload, dict):
        return None
    for key in ("seven_day_fable", "seven_day_overage_included"):
        parsed = parse_window(payload.get(key), "oauth", now)
        if parsed is not None:
            return parsed
    for entry in _scoped_entries(payload):
        scope = entry.get("scope") or {}
        model = scope.get("model") if isinstance(scope, dict) else {}
        name = model.get("display_name") if isinstance(model, dict) else ""
        name = str(name or entry.get("display_name") or entry.get("name") or "")
        if "fable" in name.casefold():
            return parse_window(entry.get("window") or entry.get("rate_limit") or entry, "oauth", now)
    return None


def parse_usage(payload: Any, now: datetime) -> ClaudeLimitsSnapshot:
    """Normalize every limit bucket returned by Claude's usage endpoint."""
    if not isinstance(payload, dict):
        return ClaudeLimitsSnapshot()
    return ClaudeLimitsSnapshot(
        five_hour=parse_window(payload.get("five_hour"), "oauth", now),
        seven_day=parse_window(payload.get("seven_day"), "oauth", now),
        fable=parse_fable(payload, now),
    )


def _account_uuid() -> str:
    try:
        data = json.loads(
            (Path.home() / ".claude.json").read_text(encoding="utf-8")
        )
        return str((data.get("oauthAccount") or {}).get("accountUuid") or "")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return ""


def _credential() -> tuple[str, int | None]:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if token:
        return token, None
    try:
        data = json.loads(
            (Path.home() / ".claude/.credentials.json").read_text(
                encoding="utf-8"
            )
        )
        oauth = data.get("claudeAiOauth") or {}
        return str(oauth.get("accessToken") or ""), int(oauth["expiresAt"]) if oauth.get("expiresAt") else None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return "", None


def _window_json(window: LimitWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    data = asdict(window)
    data["resets_at"] = window.resets_at.isoformat()
    data["updated_at"] = window.updated_at.isoformat()
    return data


def _window_from_json(data: Any) -> LimitWindow | None:
    if not isinstance(data, dict):
        return None
    used = _percent(data.get("used_percentage"))
    resets = _timestamp(data.get("resets_at"))
    updated = _timestamp(data.get("updated_at"))
    if used is None or resets is None or updated is None:
        return None
    return LimitWindow(used, resets, updated, str(data.get("source") or "cache"))


class ClaudeLimitsIntegration:
    """Own native observations, durable state, and the background Fable fetch."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_home() / "usb-lcd-dashboard/claude-limits.json"
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = False
        self._next_refresh = 0.0
        self._snapshot = self._load()

    def _load(self) -> ClaudeLimitsSnapshot:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            return ClaudeLimitsSnapshot()
        account = _account_uuid()
        if account and data.get("account_uuid") and data["account_uuid"] != account:
            return ClaudeLimitsSnapshot()
        return ClaudeLimitsSnapshot(
            five_hour=_window_from_json(data.get("five_hour")),
            seven_day=_window_from_json(data.get("seven_day")),
            fable=_window_from_json(data.get("fable")),
            status="cached",
            error="",
        )

    def _save(self, snapshot: ClaudeLimitsSnapshot) -> None:
        data = {
            "schema_version": 1,
            "account_uuid": _account_uuid(),
            "five_hour": _window_json(snapshot.five_hour),
            "seven_day": _window_json(snapshot.seven_day),
            "fable": _window_json(snapshot.fable),
            "status": snapshot.status,
        }
        with self._io_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            if os.name != "nt":
                temporary.chmod(0o600)
            os.replace(temporary, self.path)

    def configure(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
        self._wake.set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="usb-lcd-claude-limits", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=REQUEST_TIMEOUT_SECONDS + 1)
            self._thread = None

    def observe(self, provider: str, payload: dict[str, Any]) -> None:
        if provider != "claude":
            return
        limits = payload.get("rate_limits")
        if not isinstance(limits, dict):
            return
        now = datetime.now(timezone.utc)
        five = parse_window(limits.get("five_hour"), "statusline", now)
        seven = parse_window(limits.get("seven_day"), "statusline", now)
        if five is None and seven is None:
            return
        with self._lock:
            old = self._snapshot
            self._snapshot = ClaudeLimitsSnapshot(
                five_hour=five or old.five_hour,
                seven_day=seven or old.seven_day,
                fable=old.fable,
                status="current",
            )
            snapshot = self._snapshot
        try:
            self._save(snapshot)
        except OSError as exc:
            LOG.warning("Could not persist Claude limit snapshot: %s", exc)

    def snapshot(self) -> ClaudeLimitsSnapshot:
        with self._lock:
            return self._snapshot

    def _fetch_usage(self) -> ClaudeLimitsSnapshot:
        token, expires_ms = _credential()
        if not token or (expires_ms is not None and expires_ms <= int(time.time() * 1000)):
            raise RuntimeError("Claude OAuth credential unavailable or expired")
        request = urllib.request.Request(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        return parse_usage(payload, datetime.now(timezone.utc))

    def _refresh(self) -> None:
        try:
            fetched = self._fetch_usage()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = max(RATE_LIMIT_BACKOFF_SECONDS, int(retry))
                except ValueError:
                    delay = RATE_LIMIT_BACKOFF_SECONDS
                self._next_refresh = time.monotonic() + delay
                message = "Fable usage is rate limited; using cached data"
            else:
                self._next_refresh = time.monotonic() + REFRESH_SECONDS
                message = f"Fable usage request failed ({exc.code}); using cached data"
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self._next_refresh = time.monotonic() + REFRESH_SECONDS
            message = str(exc)
        else:
            self._next_refresh = time.monotonic() + REFRESH_SECONDS
            with self._lock:
                old = self._snapshot
                self._snapshot = ClaudeLimitsSnapshot(
                    fetched.five_hour or old.five_hour,
                    fetched.seven_day or old.seven_day,
                    fetched.fable or old.fable,
                    "current" if any((fetched.five_hour, fetched.seven_day, fetched.fable)) else old.status,
                    "" if fetched.fable else "Fable limit unavailable",
                )
                snapshot = self._snapshot
            try:
                self._save(snapshot)
            except OSError as exc:
                LOG.warning("Could not persist Claude limit snapshot: %s", exc)
            return
        with self._lock:
            old = self._snapshot
            self._snapshot = ClaudeLimitsSnapshot(old.five_hour, old.seven_day, old.fable, old.status, message)
        LOG.info("%s", message)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                enabled = self._enabled
            if enabled and time.monotonic() >= self._next_refresh:
                self._refresh()
            self._wake.wait(1.0 if enabled else 30.0)
            self._wake.clear()
