from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imports would be circular at runtime
    from .background import Background
    from .layout import Tile

LOG = logging.getLogger(__name__)

DEVICE_BY_ID = (
    "/dev/serial/by-id/"
    "usb-2017-2-25_UsbMonitor_USB35INCHIPSV2-if00"
)
DEFAULT_IPC_PORT = 45722
DEFAULT_ADMIN_PORT = 45723
# The editor is only ever served to this machine: it rewrites config.toml and has
# no authentication, so binding it anywhere routable would hand the panel's
# configuration to the network.
ADMIN_HOST = "127.0.0.1"

# Named after the transport rather than the panel, because the transport is the
# part that differs: "window" is a display the OS enumerates as a monitor, and
# whether the ultra-wide panel is that or another serial protocol is unknown
# until the hardware is in hand.
DISPLAY_KINDS = ("turing_rev_a", "turing_usb", "window", "simulated", "auto")

# The daemon and the hooks both run under console-less pythonw.exe on Windows,
# so any child process would otherwise allocate a console window of its own.
# Zero on POSIX, where the flag does not exist.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def config_home() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) if base else Path.home() / "AppData/Local"
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) if base else Path.home() / ".config"


def runtime_dir() -> Path:
    if os.name == "nt":
        return config_home() / "usb-lcd-dashboard"
    base = os.environ.get("XDG_RUNTIME_DIR")
    return Path(base) if base else Path("/tmp") / f"usb-lcd-dashboard-{os.getuid()}"


@dataclass(frozen=True, slots=True)
class Config:
    device: str = "AUTO" if os.name == "nt" else "/dev/turing-lcd"
    display_kind: str = "turing_rev_a"
    width: int = 480
    height: int = 320
    orientation: str = "landscape"
    brightness: int = 25
    refresh_hz: float = 2.0
    # None means "just the palette background". A Background instance is only
    # built when the config asks for one, which keeps this module free of an
    # import cycle through render.py.
    background: "Background | None" = None
    # Empty means the 3.5" panel's single full-screen layout, synthesized at load
    # time, so an existing config keeps working with no edits.
    tiles: tuple["Tile", ...] = field(default=())
    active_ttl_seconds: int = 180
    approval_ttl_seconds: int = 90
    # A tool call can run for many minutes without the session emitting anything,
    # so work in flight outlives the idle timeout.
    tool_ttl_seconds: int = 900
    # Once a session takes the screen it keeps it this long, so a chatty session
    # cannot steal the frame before a quieter one has been readable.
    switch_dwell_seconds: float = 4.0
    idle_title: str = "AI WORKBENCH"
    ipc_mode: str = "tcp" if os.name == "nt" else "unix"
    ipc_host: str = "127.0.0.1"
    ipc_port: int = DEFAULT_IPC_PORT
    # The settings editor. Loopback only, and it can rewrite this file, so it is
    # deliberately not bindable to anything routable.
    admin_enabled: bool = True
    admin_port: int = DEFAULT_ADMIN_PORT
    # The system tray icon: proof the daemon is running, and the way to stop it.
    # Windows only; there is no tray to put it in under a systemd user unit.
    tray_enabled: bool = True
    # Discord channel snowflakes are configuration, not credentials. The bot
    # token lives in a separate protected secret store.
    discord_channel_ids: tuple[str, ...] = field(default=())
    windows_notifications_enabled: bool = False
    windows_notification_app_ids: tuple[str, ...] = field(default=())
    windows_notification_include_terms: tuple[str, ...] = field(default=())
    windows_notification_exclude_terms: tuple[str, ...] = field(default=())
    # Why the configured layout was rejected, when it was loaded leniently and
    # replaced by the default. Carried rather than discarded so `doctor` can say
    # what is wrong with the file instead of reporting a layout nobody wrote.
    # Always empty on a strict load, which raises instead.
    layout_error: str = ""

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def socket_path(self) -> Path:
        return runtime_dir() / "usb-lcd-dashboard.sock"


    @property
    def ipc_address(self) -> tuple[str, int]:
        return self.ipc_host, self.ipc_port

    @property
    def frame_interval(self) -> float:
        return 1.0 / max(0.25, min(self.refresh_hz, 10.0))


DEFAULT_CONFIG_TOML = """\
[display]
kind = "{display_kind}"
device = "{device}"
width = {width}
height = {height}
orientation = "{orientation}"
brightness = {brightness}
refresh_hz = {refresh_hz}

[dashboard]
active_ttl_seconds = {active_ttl_seconds}
approval_ttl_seconds = {approval_ttl_seconds}
tool_ttl_seconds = {tool_ttl_seconds}
switch_dwell_seconds = {switch_dwell_seconds}
idle_title = "{idle_title}"

[ipc]
mode = "{ipc_mode}"
host = "{ipc_host}"
port = {ipc_port}

# The settings editor, served on 127.0.0.1 only.
[admin]
enabled = {admin_enabled}
port = {admin_port}

# The system tray icon (Windows only).
[tray]
enabled = {tray_enabled}
"""


def default_config_toml(device: str | None = None, ipc_mode: str | None = None) -> str:
    """The starting config, rendered from the Config defaults themselves.

    This used to be a literal string in install() plus two config.example.toml
    files plus these dataclass defaults — four copies of the same thing, so
    adding a key meant remembering all four. Generating from Config() means the
    examples cannot disagree with the code, and a test asserts exactly that.
    """
    cfg = Config()
    if device is not None:
        cfg = replace(cfg, device=device)
    if ipc_mode is not None:
        cfg = replace(cfg, ipc_mode=ipc_mode)
    return DEFAULT_CONFIG_TOML.format(
        device=cfg.device,
        display_kind=cfg.display_kind,
        width=cfg.width,
        height=cfg.height,
        orientation=cfg.orientation,
        brightness=cfg.brightness,
        refresh_hz=cfg.refresh_hz,
        active_ttl_seconds=cfg.active_ttl_seconds,
        approval_ttl_seconds=cfg.approval_ttl_seconds,
        tool_ttl_seconds=cfg.tool_ttl_seconds,
        switch_dwell_seconds=cfg.switch_dwell_seconds,
        idle_title=cfg.idle_title,
        ipc_mode=cfg.ipc_mode,
        ipc_host=cfg.ipc_host,
        ipc_port=cfg.ipc_port,
        admin_enabled="true" if cfg.admin_enabled else "false",
        admin_port=cfg.admin_port,
        tray_enabled="true" if cfg.tray_enabled else "false",
    )


def _toml_value(value) -> str:
    """Render a Python value as TOML.

    Only the types the config schema actually holds. bool is checked before int
    because bool is an int in Python and would otherwise come out as 1/0.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, Path):
        # Forward slashes rather than escaped backslashes: still valid on Windows
        # and far easier to read in a hand-edited file.
        return _toml_value(value.as_posix())
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def dump_config_toml(cfg: Config) -> str:
    """Serialise a Config back to a config.toml the loader accepts.

    tomllib reads but does not write, and pulling in a writer for a schema this
    small is not worth a dependency. Round-tripping is covered by a test.
    """
    lines = [
        "[display]",
        f"kind = {_toml_value(cfg.display_kind)}",
        f"device = {_toml_value(cfg.device)}",
        f"width = {_toml_value(cfg.width)}",
        f"height = {_toml_value(cfg.height)}",
        f"orientation = {_toml_value(cfg.orientation)}",
        f"brightness = {_toml_value(cfg.brightness)}",
        f"refresh_hz = {_toml_value(cfg.refresh_hz)}",
    ]
    if cfg.background is not None:
        lines += [
            "",
            "[display.background]",
            f"color = {_toml_value(cfg.background.color)}",
            f"fit = {_toml_value(cfg.background.fit)}",
        ]
        if cfg.background.image is not None:
            lines.append(f"image = {_toml_value(cfg.background.image)}")
    lines += [
        "",
        "[dashboard]",
        f"active_ttl_seconds = {_toml_value(cfg.active_ttl_seconds)}",
        f"approval_ttl_seconds = {_toml_value(cfg.approval_ttl_seconds)}",
        f"tool_ttl_seconds = {_toml_value(cfg.tool_ttl_seconds)}",
        f"switch_dwell_seconds = {_toml_value(cfg.switch_dwell_seconds)}",
        f"idle_title = {_toml_value(cfg.idle_title)}",
        "",
        "[ipc]",
        f"mode = {_toml_value(cfg.ipc_mode)}",
        f"host = {_toml_value(cfg.ipc_host)}",
        f"port = {_toml_value(cfg.ipc_port)}",
        "",
        "[admin]",
        f"enabled = {_toml_value(cfg.admin_enabled)}",
        f"port = {_toml_value(cfg.admin_port)}",
        "",
        "[tray]",
        f"enabled = {_toml_value(cfg.tray_enabled)}",
    ]
    if cfg.discord_channel_ids:
        channels = ", ".join(_toml_value(value) for value in cfg.discord_channel_ids)
        lines += ["", "[discord]", f"channel_ids = [{channels}]"]
    if (
        cfg.windows_notifications_enabled
        or cfg.windows_notification_app_ids
        or cfg.windows_notification_include_terms
        or cfg.windows_notification_exclude_terms
    ):
        lines += [
            "",
            "[windows_notifications]",
            f"enabled = {_toml_value(cfg.windows_notifications_enabled)}",
            "app_ids = ["
            + ", ".join(_toml_value(value) for value in cfg.windows_notification_app_ids)
            + "]",
            "include_terms = ["
            + ", ".join(_toml_value(value) for value in cfg.windows_notification_include_terms)
            + "]",
            "exclude_terms = ["
            + ", ".join(_toml_value(value) for value in cfg.windows_notification_exclude_terms)
            + "]",
        ]
    for tile in cfg.tiles:
        lines += [
            "",
            "[[tile]]",
            f"widget = {_toml_value(tile.widget)}",
            f"x = {_toml_value(tile.x)}",
            f"y = {_toml_value(tile.y)}",
            f"w = {_toml_value(tile.w)}",
            f"h = {_toml_value(tile.h)}",
        ]
        if tile.options:
            lines.append("[tile.options]")
            for key in sorted(tile.options):
                lines.append(f"{key} = {_toml_value(tile.options[key])}")
    return "\n".join(lines) + "\n"


def write_config(cfg: Config, path: Path | None = None) -> Path:
    """Replace config.toml in one step.

    Written to a sibling temp file and renamed, so a crash or a concurrent read
    never sees a half-written config — the daemon watches this file's mtime and
    would otherwise reload a truncated one.
    """
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(dump_config_toml(cfg), encoding="utf-8")
    os.replace(temp, target)
    return target


def default_path() -> Path:
    override = os.environ.get("USB_LCD_DASHBOARD_CONFIG")
    return Path(override) if override else config_home() / "usb-lcd-dashboard/config.toml"


def _parse_background(table: dict) -> "Background | None":
    from .background import FIT_MODES, Background

    if not table:
        return None
    fit = str(table.get("fit", "cover"))
    if fit not in FIT_MODES:
        raise ValueError(
            "display.background.fit must be one of " + ", ".join(FIT_MODES)
        )
    raw_image = table.get("image")
    image = Path(str(raw_image)).expanduser() if raw_image else None
    if image is not None and not image.exists():
        # Not fatal: the same config may name a wallpaper that only exists on the
        # other machine, and the layer falls back to the colour.
        LOG.warning("display.background.image does not exist: %s", image)
    background = Background(fit=fit, image=image)
    if "color" in table:
        background = replace(background, color=str(table["color"]))
    return background


def _parse_tiles(raw: list) -> tuple["Tile", ...]:
    from .layout import Tile

    tiles = []
    for index, entry in enumerate(raw):
        try:
            widget = str(entry["widget"])
            options = dict(entry.get("options") or {})
            tiles.append(
                Tile(
                    widget=widget,
                    x=int(entry["x"]),
                    y=int(entry["y"]),
                    w=int(entry["w"]),
                    h=int(entry["h"]),
                    options=options,
                )
            )
        except KeyError as exc:
            raise ValueError(f"tile[{index}] is missing {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"tile[{index}] is malformed: {exc}") from exc
    return tuple(tiles)


def _with_layout(cfg: Config, *, strict: bool = True) -> Config:
    """Fill in and check the layout, defaulting to the legacy full-screen tile.

    ``strict=False`` keeps everything else in the config and substitutes the
    default layout when the configured one will not validate. That is for the
    callers that never draw a tile — see load_config.
    """
    from .layout import Tile, validate

    default = (Tile("legacy", 0, 0, cfg.width, cfg.height),)
    tiles = cfg.tiles or default
    try:
        validate(tiles, cfg.size)
    except ValueError as exc:
        if strict:
            raise
        LOG.warning("Ignoring an unusable layout (%s); this command does not draw", exc)
        return replace(cfg, tiles=default, layout_error=str(exc))
    return replace(cfg, tiles=tiles)


def load_config(path: Path | None = None, *, strict: bool = True) -> Config:
    """Load the config, validating the layout only when the caller draws it.

    ``strict=False`` is for the commands that need nothing but the IPC address
    and the paths — the hooks, and install/uninstall. A tile rect is a display
    setting, and letting one fail those commands means a single bad widget name
    makes *every* hook in *every* Claude and Codex session dump a traceback, and
    blocks the very command that would repair the file. Everything except the
    layout is still validated, because a wrong ipc.port would silently send the
    events nowhere.
    """
    selected = path or default_path()
    if not selected.exists():
        cfg = Config()
        if not Path(cfg.device).exists() and Path(DEVICE_BY_ID).exists():
            cfg = replace(cfg, device=DEVICE_BY_ID)
        return _with_layout(cfg, strict=strict)

    with selected.open("rb") as handle:
        data = tomllib.load(handle)
    return parse_config(data, strict=strict)


def parse_config_text(text: str) -> Config:
    """Validate a config document without going through the filesystem.

    The settings editor uses this so a candidate config is checked by exactly the
    same code that loads one, rather than a second copy of the rules.
    """
    return parse_config(tomllib.loads(text))


def parse_config(data: dict, *, strict: bool = True) -> Config:
    cfg = Config()
    display = data.get("display", {})
    dashboard = data.get("dashboard", {})
    ipc = data.get("ipc", {})
    admin = data.get("admin", {})
    tray = data.get("tray", {})
    discord = data.get("discord", {})
    windows_notifications = data.get("windows_notifications", {})
    raw_channel_ids = discord.get("channel_ids", [])
    if not isinstance(raw_channel_ids, list):
        raise ValueError("discord.channel_ids must be a list")
    channel_ids = tuple(dict.fromkeys(str(value).strip() for value in raw_channel_ids))
    if any(not value.isdigit() for value in channel_ids):
        raise ValueError("discord.channel_ids must contain Discord numeric IDs")
    def string_list(table: dict, key: str) -> tuple[str, ...]:
        raw = table.get(key, [])
        if not isinstance(raw, list):
            raise ValueError(f"windows_notifications.{key} must be a list")
        return tuple(dict.fromkeys(str(value).strip() for value in raw if str(value).strip()))

    notification_app_ids = string_list(windows_notifications, "app_ids")
    notification_include_terms = string_list(windows_notifications, "include_terms")
    notification_exclude_terms = string_list(windows_notifications, "exclude_terms")
    cfg = replace(
        cfg,
        device=str(display.get("device", cfg.device)),
        display_kind=str(display.get("kind", cfg.display_kind)),
        width=int(display.get("width", cfg.width)),
        height=int(display.get("height", cfg.height)),
        background=_parse_background(display.get("background") or {}),
        tiles=_parse_tiles(data.get("tile") or []),
        orientation=str(display.get("orientation", cfg.orientation)),
        brightness=int(display.get("brightness", cfg.brightness)),
        refresh_hz=float(display.get("refresh_hz", cfg.refresh_hz)),
        active_ttl_seconds=int(
            dashboard.get("active_ttl_seconds", cfg.active_ttl_seconds)
        ),
        approval_ttl_seconds=int(
            dashboard.get("approval_ttl_seconds", cfg.approval_ttl_seconds)
        ),
        tool_ttl_seconds=int(dashboard.get("tool_ttl_seconds", cfg.tool_ttl_seconds)),
        switch_dwell_seconds=float(
            dashboard.get("switch_dwell_seconds", cfg.switch_dwell_seconds)
        ),
        idle_title=str(dashboard.get("idle_title", cfg.idle_title)),
        ipc_mode=str(ipc.get("mode", cfg.ipc_mode)),
        ipc_host=str(ipc.get("host", cfg.ipc_host)),
        ipc_port=int(ipc.get("port", cfg.ipc_port)),
        admin_enabled=bool(admin.get("enabled", cfg.admin_enabled)),
        admin_port=int(admin.get("port", cfg.admin_port)),
        tray_enabled=bool(tray.get("enabled", cfg.tray_enabled)),
        discord_channel_ids=channel_ids,
        windows_notifications_enabled=bool(windows_notifications.get("enabled", False)),
        windows_notification_app_ids=notification_app_ids,
        windows_notification_include_terms=notification_include_terms,
        windows_notification_exclude_terms=notification_exclude_terms,
    )
    if cfg.orientation not in {"portrait", "landscape"}:
        raise ValueError("display.orientation must be portrait or landscape")
    if not 0 <= cfg.brightness <= 50:
        raise ValueError("display.brightness must be between 0 and 50")
    if cfg.display_kind not in DISPLAY_KINDS:
        raise ValueError("display.kind must be one of " + ", ".join(DISPLAY_KINDS))
    if not 1 <= cfg.width <= 4096 or not 1 <= cfg.height <= 4096:
        raise ValueError("display.width and display.height must be between 1 and 4096")
    if cfg.ipc_mode not in {"unix", "tcp"}:
        raise ValueError("ipc.mode must be unix or tcp")
    if not 1024 <= cfg.ipc_port <= 65535:
        raise ValueError("ipc.port must be between 1024 and 65535")
    if not 1024 <= cfg.admin_port <= 65535:
        raise ValueError("admin.port must be between 1024 and 65535")
    if cfg.admin_port == cfg.ipc_port:
        raise ValueError("admin.port and ipc.port must differ")
    return _with_layout(cfg, strict=strict)

