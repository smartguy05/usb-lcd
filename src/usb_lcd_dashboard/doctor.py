from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from serial.tools.list_ports import comports

from .config import Config
from .display import Display
from .layout import agent_slots
from .render import BACKGROUND, CLAUDE, CODEX, MUTED, PANEL, TEXT, _fit


TARGET_VID = 0x1A86
TARGET_PID = 0x5722
TARGET_SERIAL = "USB35INCHIPSV2"


def _hook_present(path: Path) -> bool:
    try:
        text = path.read_text()
        return "usb-lcd-dashboard emit" in text or "usb_lcd_dashboard emit" in text
    except OSError:
        return False


def detected_device(config: Config) -> str | None:
    configured = config.device
    if configured.upper() != "AUTO":
        if os.name == "nt":
            for port in comports():
                if port.device.casefold() == configured.casefold():
                    return port.device
            return None
        return configured if Path(configured).exists() else None

    ports = list(comports())
    for port in ports:
        if port.serial_number == TARGET_SERIAL:
            return port.device
    for port in ports:
        if port.vid == TARGET_VID and port.pid == TARGET_PID:
            return port.device
    return None


def _windows_startup_shortcut() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData/Roaming"
    return root / "Microsoft/Windows/Start Menu/Programs/Startup/USB LCD Dashboard.lnk"


def checks(config: Config) -> list[tuple[str, bool, str]]:
    resolved = detected_device(config)
    slots = agent_slots(config.tiles)
    items = [
        (
            "device",
            resolved is not None,
            resolved or f"waiting for {TARGET_VID:04x}:{TARGET_PID:04x}",
        ),
        (
            "layout",
            # A layout with nowhere to put a session would show the panel
            # nothing but decoration, which is worth flagging. A layout that
            # will not load at all is worth reporting rather than crashing on:
            # this is the command you run *because* something is wrong.
            not config.layout_error and slots > 0,
            config.layout_error
            or (
                f"{config.display_kind} {config.width}x{config.height} · "
                f"{len(config.tiles)} tiles · {slots} agent slots"
            ),
        ),
        (
            "Claude hooks",
            _hook_present(Path.home() / ".claude/settings.json"),
            "~/.claude/settings.json",
        ),
        (
            "Codex hooks",
            _hook_present(Path.home() / ".codex/hooks.json"),
            "~/.codex/hooks.json",
        ),
    ]
    if os.name == "nt":
        shortcut = _windows_startup_shortcut()
        items.append(("login autostart", shortcut.exists(), str(shortcut)))
        return items

    device = Path(resolved or config.device)
    items.insert(
        1,
        (
            "read/write access",
            resolved is not None and os.access(device, os.R_OK | os.W_OK),
            str(device),
        ),
    )
    items.append(
        ("systemd", shutil.which("systemctl") is not None, "systemctl --user")
    )
    if shutil.which("systemctl"):
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "usb-lcd-dashboard.service"],
            capture_output=True,
            text=True,
            check=False,
        )
        items.append(("service", result.returncode == 0, result.stdout.strip() or "inactive"))
    return items


def paint_test(config: Config) -> None:
    """Put a card on the panel describing what the daemon thinks it is talking to.

    Every line is derived rather than hardcoded, so this stays useful on a panel
    that is not the 3.5" Turing — the old version drew a 480x320 card with the
    Turing's USB id baked into it.
    """
    display = Display(config)
    try:
        display.connect()
        width, height = display.size
        pad = max(12, round(width * 0.045))
        frame = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle(
            (pad, pad, width - pad, height - pad),
            radius=max(8, round(min(width, height) * 0.07)),
            fill=PANEL,
        )
        inner = max(1, width - 4 * pad)
        lines = [
            ("USB LCD READY", round(height * 0.119), True, CODEX),
            (f"{config.display_kind} · {display.device}", round(height * 0.056), False, TEXT),
            (
                f"{config.orientation.upper()} {width} × {height}",
                round(height * 0.072),
                True,
                MUTED,
            ),
            (
                f"{len(config.tiles)} TILES · {agent_slots(config.tiles)} AGENT SLOTS",
                round(height * 0.056),
                True,
                MUTED,
            ),
            ("Claude Code + Codex", round(height * 0.075), True, CLAUDE),
        ]
        y = pad * 2
        for text, size, bold, colour in lines:
            fitted, font = _fit(draw, text, inner, max(9, size), bold, min_size=9)
            draw.text((pad * 2, y), fitted, font=font, fill=colour)
            y += round(max(9, size) * 1.65)
        display.paint(frame, force=True)
    finally:
        display.close()


def print_report(config: Config) -> bool:
    results = checks(config)
    for label, passed, detail in results:
        status = "OK" if passed else "FAIL"
        print(f"{status:4}  {label:18} {detail}")
    return all(item[1] for item in results)
