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
DISPLAY_KINDS = ("turing_rev_a", "window", "simulated", "auto")

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
            tiles.append(
                Tile(
                    widget=str(entry["widget"]),
                    x=int(entry["x"]),
                    y=int(entry["y"]),
                    w=int(entry["w"]),
                    h=int(entry["h"]),
                    options=dict(entry.get("options") or {}),
                )
            )
        except KeyError as exc:
            raise ValueError(f"tile[{index}] is missing {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"tile[{index}] is malformed: {exc}") from exc
    return tuple(tiles)


def _with_layout(cfg: Config) -> Config:
    """Fill in and check the layout, defaulting to the legacy full-screen tile."""
    from .layout import Tile, validate

    tiles = cfg.tiles or (Tile("legacy", 0, 0, cfg.width, cfg.height),)
    validate(tiles, cfg.size)
    return replace(cfg, tiles=tiles)


def load_config(path: Path | None = None) -> Config:
    selected = path or default_path()
    if not selected.exists():
        cfg = Config()
        if not Path(cfg.device).exists() and Path(DEVICE_BY_ID).exists():
            cfg = replace(cfg, device=DEVICE_BY_ID)
        return _with_layout(cfg)

    with selected.open("rb") as handle:
        data = tomllib.load(handle)
    return parse_config(data)


def parse_config_text(text: str) -> Config:
    """Validate a config document without going through the filesystem.

    The settings editor uses this so a candidate config is checked by exactly the
    same code that loads one, rather than a second copy of the rules.
    """
    return parse_config(tomllib.loads(text))


def parse_config(data: dict) -> Config:
    cfg = Config()
    display = data.get("display", {})
    dashboard = data.get("dashboard", {})
    ipc = data.get("ipc", {})
    admin = data.get("admin", {})
    tray = data.get("tray", {})
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
    return _with_layout(cfg)

