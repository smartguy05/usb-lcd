"""The settings editor: a small HTTP server the daemon runs on loopback.

Free-pixel tile rects are quick to render and awkward to type, so the editor
exists to drag them instead. It runs inside the daemon so the preview can be the
frame actually on the panel rather than a mock-up.

It writes config.toml and has no authentication, so it binds 127.0.0.1 only and
refuses any request whose Host header is not loopback — that last part blunts DNS
rebinding, where a page on the open web resolves its own hostname to 127.0.0.1
and talks to this server through the browser.
"""

from __future__ import annotations

import io
import hashlib
import json
import logging
import os
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps, UnidentifiedImageError

from .admin_page import PAGE
from .background import Background
from .config import (
    ADMIN_HOST,
    ActiveBackgroundConfig,
    Config,
    dump_config_toml,
    parse_config_text,
    write_config,
)
from .layout import Tile
from .orientation import ORIENTATIONS, rotate_layout
from .widgets import describe
from .todos import TodoStore

LOG = logging.getLogger(__name__)

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
MAX_BODY_BYTES = 256 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
# How much of an over-sized body to swallow so the 413 actually reaches the
# client rather than racing an unread request into a connection reset.
DRAIN_LIMIT = 4 * 1024 * 1024


def _host_is_loopback(header: str | None) -> bool:
    if not header:
        return False
    host = header.strip()
    if host.startswith("["):
        # Bracketed IPv6, "[::1]:45723" — the brackets are kept, since that is
        # how the literal is written, and only the port is dropped.
        end = host.find("]")
        if end == -1:
            return False
        host = host[: end + 1]
    elif ":" in host:
        host = host.split(":", 1)[0]
    return host.lower() in ALLOWED_HOSTS


def config_to_json(cfg: Config) -> dict[str, Any]:
    return {
        "display": {
            "kind": cfg.display_kind,
            "device": cfg.device,
            "width": cfg.width,
            "height": cfg.height,
            "orientation": cfg.orientation,
            "brightness": cfg.brightness,
            "refresh_hz": cfg.refresh_hz,
        },
        "background": None
        if cfg.background is None
        else {
            "color": cfg.background.color,
            "image": None
            if cfg.background.image is None
            else cfg.background.image.as_posix(),
            "fit": cfg.background.fit,
            "card_opacity": cfg.background.card_opacity,
        },
        "active_background": None
        if cfg.active_background is None
        else {
            "enabled": cfg.active_background.enabled,
            "scale": cfg.active_background.scale,
            "speed_min": cfg.active_background.speed_min,
            "speed_max": cfg.active_background.speed_max,
            "opacity": cfg.active_background.opacity,
        },
        "screensaver": {
            "enabled": cfg.screensaver_enabled,
            "idle_seconds": cfg.screensaver_idle_seconds,
        },
        "dashboard": {
            "active_ttl_seconds": cfg.active_ttl_seconds,
            "approval_ttl_seconds": cfg.approval_ttl_seconds,
            "tool_ttl_seconds": cfg.tool_ttl_seconds,
            "switch_dwell_seconds": cfg.switch_dwell_seconds,
            "idle_title": cfg.idle_title,
        },
        "discord": {"channel_ids": list(cfg.discord_channel_ids)},
        "windows_notifications": {
            "enabled": cfg.windows_notifications_enabled,
            "app_ids": list(cfg.windows_notification_app_ids),
            "include_terms": list(cfg.windows_notification_include_terms),
            "exclude_terms": list(cfg.windows_notification_exclude_terms),
        },
        # Shown but not editable: changing the IPC transport would orphan the
        # installed hooks, and changing the admin port would cut off this page.
        "readonly": {
            "ipc_mode": cfg.ipc_mode,
            "ipc_host": cfg.ipc_host,
            "ipc_port": cfg.ipc_port,
            "admin_port": cfg.admin_port,
        },
        "tiles": [
            {
                "widget": tile.widget,
                "x": tile.x,
                "y": tile.y,
                "w": tile.w,
                "h": tile.h,
                "options": dict(tile.options),
            }
            for tile in cfg.tiles
        ],
    }


def config_from_json(current: Config, payload: dict[str, Any]) -> Config:
    """Build a candidate Config from the editor's JSON.

    Only shape errors are raised here. Every value rule is left to the loader,
    which this candidate is round-tripped through by save().
    """
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    display = payload.get("display") or {}
    dashboard = payload.get("dashboard") or {}
    screensaver = payload.get("screensaver") or {}
    discord = payload.get("discord") or {}
    windows_notifications = payload.get("windows_notifications") or {}
    raw_channel_ids = discord.get("channel_ids", current.discord_channel_ids)
    if not isinstance(raw_channel_ids, (list, tuple)):
        raise ValueError("discord.channel_ids must be a list")
    def string_values(key, fallback):
        raw = windows_notifications.get(key, fallback)
        if not isinstance(raw, (list, tuple)):
            raise ValueError(f"windows_notifications.{key} must be a list")
        return tuple(str(value) for value in raw)
    raw_tiles = payload.get("tiles")
    if not isinstance(raw_tiles, list):
        raise ValueError("tiles must be a list")
    if not raw_tiles:
        # The loader synthesizes the legacy full-screen tile when a config has no
        # [[tile]] at all, so that existing installs keep working. Saving an empty
        # layout from the editor would silently land a 3.5" card on a wide panel,
        # which is not what deleting every tile means.
        raise ValueError("a layout needs at least one tile")

    tiles = []
    for index, entry in enumerate(raw_tiles):
        if not isinstance(entry, dict):
            raise ValueError(f"tile[{index}] must be an object")
        options = entry.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError(f"tile[{index}].options must be an object")
        try:
            tiles.append(
                Tile(
                    widget=str(entry["widget"]),
                    x=int(entry["x"]),
                    y=int(entry["y"]),
                    w=int(entry["w"]),
                    h=int(entry["h"]),
                    options={str(k): v for k, v in options.items()},
                )
            )
        except KeyError as exc:
            raise ValueError(f"tile[{index}] is missing {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"tile[{index}] is malformed: {exc}") from exc

    def number(source, key, cast, fallback):
        if key not in source:
            return fallback
        try:
            return cast(source[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a number") from exc

    raw_background = payload.get("background")
    background = None
    if isinstance(raw_background, dict):
        image = raw_background.get("image") or None
        background = Background(
            color=str(raw_background.get("color", Background().color)),
            image=Path(str(image)).expanduser() if image else None,
            fit=str(raw_background.get("fit", "cover")),
            card_opacity=number(raw_background, "card_opacity", float, Background().card_opacity),
        )

    raw_active_bg = payload.get("active_background")
    active_background = None
    if isinstance(raw_active_bg, dict):
        default = ActiveBackgroundConfig()
        active_background = ActiveBackgroundConfig(
            enabled=bool(raw_active_bg.get("enabled", True)),
            scale=number(raw_active_bg, "scale", float, default.scale),
            speed_min=number(raw_active_bg, "speed_min", float, default.speed_min),
            speed_max=number(raw_active_bg, "speed_max", float, default.speed_max),
            opacity=number(raw_active_bg, "opacity", float, default.opacity),
        )

    return replace(
        current,
        display_kind=str(display.get("kind", current.display_kind)),
        device=str(display.get("device", current.device)),
        width=number(display, "width", int, current.width),
        height=number(display, "height", int, current.height),
        orientation=str(display.get("orientation", current.orientation)),
        brightness=number(display, "brightness", int, current.brightness),
        refresh_hz=number(display, "refresh_hz", float, current.refresh_hz),
        background=background,
        active_ttl_seconds=number(
            dashboard, "active_ttl_seconds", int, current.active_ttl_seconds
        ),
        approval_ttl_seconds=number(
            dashboard, "approval_ttl_seconds", int, current.approval_ttl_seconds
        ),
        tool_ttl_seconds=number(
            dashboard, "tool_ttl_seconds", int, current.tool_ttl_seconds
        ),
        switch_dwell_seconds=number(
            dashboard, "switch_dwell_seconds", float, current.switch_dwell_seconds
        ),
        idle_title=str(dashboard.get("idle_title", current.idle_title)),
        active_background=active_background,
        screensaver_enabled=bool(
            screensaver.get("enabled", current.screensaver_enabled)
        ),
        screensaver_idle_seconds=number(
            screensaver, "idle_seconds", int, current.screensaver_idle_seconds
        ),
        discord_channel_ids=tuple(str(value) for value in raw_channel_ids),
        windows_notifications_enabled=bool(
            windows_notifications.get("enabled", current.windows_notifications_enabled)
        ),
        windows_notification_app_ids=string_values(
            "app_ids", current.windows_notification_app_ids
        ),
        windows_notification_include_terms=string_values(
            "include_terms", current.windows_notification_include_terms
        ),
        windows_notification_exclude_terms=string_values(
            "exclude_terms", current.windows_notification_exclude_terms
        ),
        tiles=tuple(tiles),
    )


class AdminState:
    """What the editor needs from the daemon, and nothing more."""

    def __init__(
        self,
        config_path: Path,
        get_config: Callable[[], Config],
        get_preview: Callable[[], Image.Image | None],
        get_discord: Callable[[], dict[str, Any]] | None = None,
        save_discord_token: Callable[[str], dict[str, Any]] | None = None,
        disconnect_discord: Callable[[], dict[str, Any]] | None = None,
        refresh_discord_channels: Callable[[], Any] | None = None,
        clear_discord: Callable[[], dict[str, Any]] | None = None,
        get_windows_notifications: Callable[[], dict[str, Any]] | None = None,
        request_windows_notification_access: Callable[[], dict[str, Any]] | None = None,
        request_display_reconnect: Callable[[], bool] | None = None,
        todo_store: TodoStore | None = None,
    ):
        self.config_path = config_path
        self.get_config = get_config
        self.get_preview = get_preview
        self.get_discord = get_discord or (lambda: {
            "configured": False, "status": "unconfigured", "bot": "",
            "updated_at": None, "new_messages": 0, "stale": False,
            "error": "", "channels": [], "selected_channel_ids": [],
        })
        self.save_discord_token = save_discord_token
        self.disconnect_discord = disconnect_discord
        self.refresh_discord_channels = refresh_discord_channels
        self.clear_discord = clear_discord
        self.get_windows_notifications = get_windows_notifications or (
            lambda: {"status": "unsupported", "error": "", "updated_at": None, "apps": [], "matching": 0}
        )
        self.request_windows_notification_access = request_windows_notification_access
        self.request_display_reconnect = request_display_reconnect
        self.todo_store = todo_store

    def save(self, payload: dict[str, Any]) -> Config:
        """Validate through the loader, then replace config.toml atomically."""
        candidate = config_from_json(self.get_config(), payload)
        # Round-tripping through the real loader means the editor cannot accept a
        # config the daemon would then refuse to start on.
        validated = parse_config_text(dump_config_toml(candidate))
        write_config(validated, self.config_path)
        self._prune_managed_backgrounds(
            validated.background.image if validated.background is not None else None
        )
        return validated

    @property
    def background_dir(self) -> Path:
        return self.config_path.parent / "backgrounds"

    def save_background(self, raw: bytes) -> Path:
        if not raw:
            raise ValueError("image upload is empty")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image upload must be 10 MiB or smaller")
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                if opened.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("background must be PNG, JPEG, or WebP")
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("background must be 25 megapixels or smaller")
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("background is not a readable image") from exc
        digest = hashlib.sha256(raw).hexdigest()[:20]
        self.background_dir.mkdir(parents=True, exist_ok=True)
        target = self.background_dir / f"wallpaper-{digest}.png"
        if not target.exists():
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(buffer.getvalue())
            os.replace(temporary, target)
        return target

    def _prune_managed_backgrounds(self, keep: Path | None) -> None:
        if not self.background_dir.exists():
            return
        try:
            keep_resolved = keep.resolve() if keep is not None else None
        except OSError:
            keep_resolved = None
        for candidate in self.background_dir.glob("wallpaper-*.png"):
            try:
                if candidate.resolve() != keep_resolved:
                    candidate.unlink()
            except OSError as exc:
                LOG.warning("Could not prune old background %s: %s", candidate, exc)


def rotate_layout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        source = str(payload["source"])
        target = str(payload["target"])
        size = (int(payload["width"]), int(payload["height"]))
        tiles = payload["tiles"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("rotation needs source, target, width, height, and tiles") from exc
    if source not in ORIENTATIONS or target not in ORIENTATIONS:
        raise ValueError("unknown display orientation")
    if not isinstance(tiles, list):
        raise ValueError("tiles must be a list")
    rects = []
    for index, tile in enumerate(tiles):
        try:
            rects.append(tuple(int(tile[key]) for key in ("x", "y", "w", "h")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"tile[{index}] has an invalid rectangle") from exc
    new_size, rotated = rotate_layout(size, rects, source, target)
    result_tiles = []
    for tile, rect in zip(tiles, rotated):
        result_tiles.append({**tile, **dict(zip(("x", "y", "w", "h"), rect))})
    return {"width": new_size[0], "height": new_size[1], "tiles": result_tiles}


def make_handler(state: AdminState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "usb-lcd-admin"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # noqa: A003 - base class name
            LOG.debug("admin %s", fmt % args)

        # -- helpers ---------------------------------------------------------
        def _send(self, code, body: bytes, content_type: str, cache=False):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if not cache:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, payload):
            self._send(code, json.dumps(payload).encode(), "application/json")

        def _guard(self) -> bool:
            if _host_is_loopback(self.headers.get("Host")):
                return True
            self._json(403, {"error": "this editor only serves 127.0.0.1"})
            return False

        def _read_json(self) -> dict[str, Any] | None:
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                self._json(415, {"error": "todo actions require JSON"})
                return None
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "bad Content-Length"})
                return None
            if length > MAX_BODY_BYTES:
                self._json(413, {"error": "request is implausibly large"})
                return None
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                self._json(400, {"error": f"invalid JSON: {exc}"})
                return None
            if not isinstance(payload, dict):
                self._json(400, {"error": "JSON body must be an object"})
                return None
            return payload

        def _read_upload(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "bad Content-Length"})
                return None
            if length > MAX_IMAGE_BYTES:
                remaining = min(length, MAX_IMAGE_BYTES + 1)
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self.close_connection = True
                self._json(413, {"error": "image upload must be 10 MiB or smaller"})
                return None
            return self.rfile.read(length) if length else b""

        def _todo_store(self) -> TodoStore | None:
            if state.todo_store is None:
                self._json(503, {"error": "todo storage is unavailable"})
                return None
            return state.todo_store

        def _todo_error(self, exc: Exception) -> None:
            if isinstance(exc, KeyError):
                self._json(404, {"error": "no such todo"})
            elif isinstance(exc, ValueError):
                self._json(400, {"error": str(exc)})
            else:
                LOG.exception("Todo action failed")
                self._json(500, {"error": "todo storage failed"})

        # -- routes ----------------------------------------------------------
        def do_GET(self):  # noqa: N802 - base class name
            if not self._guard():
                return
            route = self.path.split("?", 1)[0]
            if route in ("/", "/index.html"):
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif route == "/api/config":
                self._json(200, config_to_json(state.get_config()))
            elif route == "/api/widgets":
                self._json(200, {"widgets": describe()})
            elif route == "/api/integrations/discord":
                self._json(200, state.get_discord())
            elif route == "/api/integrations/windows-notifications":
                self._json(200, state.get_windows_notifications())
            elif route == "/api/todos":
                store = self._todo_store()
                if store is not None:
                    include_completed = "include_completed=1" in self.path.split("?", 1)[-1]
                    self._json(200, {"todos": [item.to_json() for item in store.list(include_completed)]})
            elif route == "/api/preview.png":
                frame = state.get_preview()
                if frame is None:
                    self._json(503, {"error": "no frame has been rendered yet"})
                    return
                buffer = io.BytesIO()
                frame.save(buffer, format="PNG")
                self._send(200, buffer.getvalue(), "image/png")
            else:
                self._json(404, {"error": "no such route"})

        def do_POST(self):  # noqa: N802 - base class name
            if not self._guard():
                return
            route = self.path.split("?", 1)[0]
            if route == "/api/layout/rotate":
                payload = self._read_json()
                if payload is None:
                    return
                try:
                    self._json(200, rotate_layout_payload(payload))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if route == "/api/background-image":
                raw = self._read_upload()
                if raw is None:
                    return
                try:
                    image_path = state.save_background(raw)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                except OSError as exc:
                    LOG.exception("Could not store background image")
                    self._json(500, {"error": f"could not store background: {exc}"})
                    return
                self._json(201, {"image": image_path.as_posix()})
                return
            if route == "/api/display/reconnect":
                if self._read_json() is None:
                    return
                if state.request_display_reconnect is None:
                    self._json(503, {"error": "display reconnect is unavailable"})
                    return
                try:
                    accepted = state.request_display_reconnect()
                except Exception as exc:
                    LOG.exception("Display reconnect request failed")
                    self._json(502, {"error": str(exc)})
                    return
                if not accepted:
                    self._json(503, {"error": "daemon did not accept reconnect request"})
                    return
                self._json(202, {"accepted": True})
                return
            if route == "/api/todos" or route.startswith("/api/todos/"):
                store = self._todo_store()
                if store is None:
                    return
                payload = self._read_json()
                if payload is None:
                    return
                try:
                    if route == "/api/todos":
                        item = store.create(
                            payload.get("title"), payload.get("details", ""),
                            payload.get("priority", "normal"), payload.get("due_date"),
                        )
                        self._json(201, {"todo": item.to_json()})
                    elif route == "/api/todos/reorder":
                        items = store.reorder(payload.get("ordered_ids") or [])
                        self._json(200, {"todos": [item.to_json() for item in items]})
                    else:
                        parts = route.strip("/").split("/")
                        if len(parts) != 4 or parts[3] not in ("complete", "reopen"):
                            self._json(404, {"error": "no such route"})
                            return
                        item = store.set_completed(parts[2], parts[3] == "complete")
                        self._json(200, {"todo": item.to_json()})
                except Exception as exc:
                    self._todo_error(exc)
                return
            if route == "/api/integrations/windows-notifications/access":
                if not (self.headers.get("Content-Type") or "").lower().startswith(
                    "application/json"
                ):
                    self._json(415, {"error": "integration actions require JSON"})
                    return
                if state.request_windows_notification_access is None:
                    self._json(503, {"error": "Windows notification integration is unavailable"})
                    return
                try:
                    result = state.request_windows_notification_access()
                except Exception as exc:
                    LOG.exception("Windows notification access request failed")
                    self._json(502, {"error": str(exc)})
                    return
                self._json(200, result)
                return
            if route.startswith("/api/integrations/discord/"):
                if not (self.headers.get("Content-Type") or "").lower().startswith(
                    "application/json"
                ):
                    self._json(415, {"error": "integration actions require JSON"})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > MAX_BODY_BYTES:
                        self._json(413, {"error": "request is implausibly large"})
                        return
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if route.endswith("/token"):
                        if state.save_discord_token is None:
                            raise RuntimeError("Discord integration is unavailable")
                        result = state.save_discord_token(str(payload.get("token") or ""))
                    elif route.endswith("/disconnect"):
                        if state.disconnect_discord is None:
                            raise RuntimeError("Discord integration is unavailable")
                        result = state.disconnect_discord()
                    elif route.endswith("/channels"):
                        if state.refresh_discord_channels is None:
                            raise RuntimeError("Discord integration is unavailable")
                        state.refresh_discord_channels()
                        result = state.get_discord()
                    elif route.endswith("/clear"):
                        if state.clear_discord is None:
                            raise RuntimeError("Discord integration is unavailable")
                        result = state.clear_discord()
                    else:
                        self._json(404, {"error": "no such route"})
                        return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                except Exception as exc:
                    LOG.exception("Discord integration action failed")
                    self._json(502, {"error": str(exc)})
                    return
                self._json(200, result if isinstance(result, dict) else state.get_discord())
                return
            if route != "/api/config":
                self._json(404, {"error": "no such route"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "bad Content-Length"})
                return
            if length > MAX_BODY_BYTES:
                # Drain what the client is already sending before answering,
                # otherwise the reply races the request and the connection is
                # reset instead of delivering the status. Beyond the drain cap,
                # hang up rather than read an unbounded body.
                remaining = min(length, DRAIN_LIMIT)
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self.close_connection = True
                self._json(413, {"error": "config is implausibly large"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                self._json(400, {"error": f"invalid JSON: {exc}"})
                return
            try:
                saved = state.save(payload)
            except ValueError as exc:
                # The layout rules report which tile is at fault, so pass the
                # message straight through rather than flattening it.
                self._json(400, {"error": str(exc)})
                return
            except OSError as exc:
                LOG.exception("Could not write the config")
                self._json(500, {"error": f"could not write the config: {exc}"})
                return
            LOG.info("Config saved from the editor: %s", state.config_path)
            self._json(200, {"saved": True, "config": config_to_json(saved)})

        def do_PATCH(self):  # noqa: N802 - base class name
            if not self._guard():
                return
            route = self.path.split("?", 1)[0]
            parts = route.strip("/").split("/")
            if len(parts) != 3 or parts[:2] != ["api", "todos"]:
                self._json(404, {"error": "no such route"})
                return
            store = self._todo_store()
            if store is None:
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                item = store.update(parts[2], **payload)
            except Exception as exc:
                self._todo_error(exc)
                return
            self._json(200, {"todo": item.to_json()})

        def do_DELETE(self):  # noqa: N802 - base class name
            if not self._guard():
                return
            route = self.path.split("?", 1)[0]
            parts = route.strip("/").split("/")
            if len(parts) != 3 or parts[:2] != ["api", "todos"]:
                self._json(404, {"error": "no such route"})
                return
            store = self._todo_store()
            if store is None:
                return
            payload = self._read_json()
            if payload is None:
                return
            if payload.get("confirm") is not True:
                self._json(400, {"error": "permanent deletion requires confirm=true"})
                return
            try:
                store.delete(parts[2])
            except Exception as exc:
                self._todo_error(exc)
                return
            self._json(200, {"deleted": True})

    return Handler


def start(state: AdminState, port: int) -> ThreadingHTTPServer:
    """Serve the editor on a daemon thread, so it never holds up shutdown."""
    server = ThreadingHTTPServer((ADMIN_HOST, port), make_handler(state))
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, name="usb-lcd-admin", daemon=True
    )
    thread.start()
    LOG.info("Settings editor on http://%s:%s", ADMIN_HOST, port)
    return server
