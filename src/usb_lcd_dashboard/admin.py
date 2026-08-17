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
import json
import logging
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .admin_page import PAGE
from .background import Background
from .config import ADMIN_HOST, Config, dump_config_toml, parse_config_text, write_config
from .layout import Tile
from .widgets import describe

LOG = logging.getLogger(__name__)

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
MAX_BODY_BYTES = 256 * 1024
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
        },
        "dashboard": {
            "active_ttl_seconds": cfg.active_ttl_seconds,
            "approval_ttl_seconds": cfg.approval_ttl_seconds,
            "tool_ttl_seconds": cfg.tool_ttl_seconds,
            "switch_dwell_seconds": cfg.switch_dwell_seconds,
            "idle_title": cfg.idle_title,
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

    raw_background = payload.get("background")
    background = None
    if isinstance(raw_background, dict):
        image = raw_background.get("image") or None
        background = Background(
            color=str(raw_background.get("color", Background().color)),
            image=Path(str(image)).expanduser() if image else None,
            fit=str(raw_background.get("fit", "cover")),
        )

    def number(source, key, cast, fallback):
        if key not in source:
            return fallback
        try:
            return cast(source[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a number") from exc

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
        tiles=tuple(tiles),
    )


class AdminState:
    """What the editor needs from the daemon, and nothing more."""

    def __init__(
        self,
        config_path: Path,
        get_config: Callable[[], Config],
        get_preview: Callable[[], Image.Image | None],
        get_teams: Callable[[], dict[str, Any]] | None = None,
        connect_teams: Callable[[], dict[str, Any]] | None = None,
        disconnect_teams: Callable[[], None] | None = None,
    ):
        self.config_path = config_path
        self.get_config = get_config
        self.get_preview = get_preview
        self.get_teams = get_teams or (
            lambda: {
                "configured": False,
                "status": "unconfigured",
                "account": "",
                "updated_at": None,
                "unread_conversations": 0,
                "stale": False,
                "error": "",
                "verification_uri": None,
                "user_code": None,
                "expires_at": None,
            }
        )
        self.connect_teams = connect_teams
        self.disconnect_teams = disconnect_teams

    def save(self, payload: dict[str, Any]) -> Config:
        """Validate through the loader, then replace config.toml atomically."""
        candidate = config_from_json(self.get_config(), payload)
        # Round-tripping through the real loader means the editor cannot accept a
        # config the daemon would then refuse to start on.
        validated = parse_config_text(dump_config_toml(candidate))
        write_config(validated, self.config_path)
        return validated


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
            elif route == "/api/integrations/teams":
                self._json(200, state.get_teams())
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
            if route in {
                "/api/integrations/teams/connect",
                "/api/integrations/teams/disconnect",
            }:
                if not (self.headers.get("Content-Type") or "").lower().startswith(
                    "application/json"
                ):
                    self._json(415, {"error": "integration actions require JSON"})
                    return
                action = (
                    state.connect_teams
                    if route.endswith("/connect")
                    else state.disconnect_teams
                )
                if action is None:
                    self._json(503, {"error": "Teams integration is unavailable"})
                    return
                try:
                    result = action()
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                except Exception as exc:
                    LOG.exception("Teams integration action failed")
                    self._json(502, {"error": str(exc)})
                    return
                self._json(200, result if isinstance(result, dict) else state.get_teams())
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
