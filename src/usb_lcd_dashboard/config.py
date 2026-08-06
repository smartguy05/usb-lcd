from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


DEVICE_BY_ID = (
    "/dev/serial/by-id/"
    "usb-2017-2-25_UsbMonitor_USB35INCHIPSV2-if00"
)
DEFAULT_IPC_PORT = 45722

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
    orientation: str = "landscape"
    brightness: int = 25
    refresh_hz: float = 2.0
    active_ttl_seconds: int = 180
    approval_ttl_seconds: int = 90
    idle_title: str = "AI WORKBENCH"
    ipc_mode: str = "tcp" if os.name == "nt" else "unix"
    ipc_host: str = "127.0.0.1"
    ipc_port: int = DEFAULT_IPC_PORT

    @property
    def socket_path(self) -> Path:
        return runtime_dir() / "usb-lcd-dashboard.sock"


    @property
    def ipc_address(self) -> tuple[str, int]:
        return self.ipc_host, self.ipc_port

    @property
    def frame_interval(self) -> float:
        return 1.0 / max(0.25, min(self.refresh_hz, 10.0))


def default_path() -> Path:
    override = os.environ.get("USB_LCD_DASHBOARD_CONFIG")
    return Path(override) if override else config_home() / "usb-lcd-dashboard/config.toml"


def load_config(path: Path | None = None) -> Config:
    selected = path or default_path()
    cfg = Config()
    if not selected.exists():
        if not Path(cfg.device).exists() and Path(DEVICE_BY_ID).exists():
            return replace(cfg, device=DEVICE_BY_ID)
        return cfg

    with selected.open("rb") as handle:
        data = tomllib.load(handle)
    display = data.get("display", {})
    dashboard = data.get("dashboard", {})
    ipc = data.get("ipc", {})
    cfg = replace(
        cfg,
        device=str(display.get("device", cfg.device)),
        orientation=str(display.get("orientation", cfg.orientation)),
        brightness=int(display.get("brightness", cfg.brightness)),
        refresh_hz=float(display.get("refresh_hz", cfg.refresh_hz)),
        active_ttl_seconds=int(
            dashboard.get("active_ttl_seconds", cfg.active_ttl_seconds)
        ),
        approval_ttl_seconds=int(
            dashboard.get("approval_ttl_seconds", cfg.approval_ttl_seconds)
        ),
        idle_title=str(dashboard.get("idle_title", cfg.idle_title)),
        ipc_mode=str(ipc.get("mode", cfg.ipc_mode)),
        ipc_host=str(ipc.get("host", cfg.ipc_host)),
        ipc_port=int(ipc.get("port", cfg.ipc_port)),
    )
    if cfg.orientation not in {"portrait", "landscape"}:
        raise ValueError("display.orientation must be portrait or landscape")
    if not 0 <= cfg.brightness <= 50:
        raise ValueError("display.brightness must be between 0 and 50")
    if cfg.ipc_mode not in {"unix", "tcp"}:
        raise ValueError("ipc.mode must be unix or tcp")
    if not 1024 <= cfg.ipc_port <= 65535:
        raise ValueError("ipc.port must be between 1024 and 65535")
    return cfg

