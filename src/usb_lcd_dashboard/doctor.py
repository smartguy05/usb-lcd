from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from serial.tools.list_ports import comports

from .config import Config
from .display import Display
from .render import HEIGHT, WIDTH, _font


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
    items = [
        (
            "device",
            resolved is not None,
            resolved or f"waiting for {TARGET_VID:04x}:{TARGET_PID:04x}",
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
    display = Display(config)
    try:
        display.connect()
        frame = Image.new("RGB", (WIDTH, HEIGHT), "#081018")
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle((20, 20, WIDTH - 20, HEIGHT - 20), radius=22, fill="#101c28")
        draw.text((44, 58), "USB LCD READY", font=_font(38, True), fill="#2bc48a")
        draw.text((44, 132), "1a86:5722 · USB35INCHIPSV2", font=_font(18), fill="#f2f7fb")
        draw.text((44, 181), "LANDSCAPE 480 × 320", font=_font(23, True), fill="#8aa0b2")
        draw.text((44, 242), "Claude Code + Codex", font=_font(24, True), fill="#d97757")
        display.paint(frame, force=True)
    finally:
        display.close()


def print_report(config: Config) -> bool:
    results = checks(config)
    for label, passed, detail in results:
        status = "OK" if passed else "FAIL"
        print(f"{status:4}  {label:18} {detail}")
    return all(item[1] for item in results)
