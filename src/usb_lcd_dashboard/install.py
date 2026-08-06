from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import config_home


COMMON_EVENTS = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "Stop",
    "SessionEnd",
]
EVENTS_BY_PROVIDER = {
    "claude": [*COMMON_EVENTS, "PostToolUseFailure"],
    "codex": COMMON_EVENTS,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temporary, path)


def _backup(path: Path) -> str | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.usb-lcd-backup-{stamp}")
    shutil.copy2(path, backup)
    return str(backup)


def _contains_ours(value: Any) -> bool:
    text = json.dumps(value)
    return "usb-lcd-dashboard" in text or "usb_lcd_dashboard" in text


def _strip_ours(groups: list[Any]) -> list[Any]:
    return [group for group in groups if not _contains_ours(group)]


def _quote_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _command_prefix(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    executable_name = (
        "usb-lcd-dashboard.exe" if os.name == "nt" else "usb-lcd-dashboard"
    )
    script = Path(sys.executable).with_name(executable_name)
    if script.exists():
        return _quote_command([str(script)])
    return _quote_command([sys.executable, "-m", "usb_lcd_dashboard"])


def _merge_hooks(settings: dict[str, Any], provider: str, command_prefix: str) -> None:
    hooks = settings.setdefault("hooks", {})
    command = f"{command_prefix} emit --provider {provider}"
    for event, groups in list(hooks.items()):
        cleaned = _strip_ours(groups)
        if cleaned:
            hooks[event] = cleaned
        else:
            hooks.pop(event, None)
    for event in EVENTS_BY_PROVIDER[provider]:
        groups = _strip_ours(hooks.get(event, []))
        groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 2,
                    }
                ]
            }
        )
        hooks[event] = groups


def install(executable: str | None = None) -> None:
    command_prefix = _command_prefix(executable)
    state_dir = config_home() / "usb-lcd-dashboard"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "install-state.json"
    state = _read_json(state_path) if state_path.exists() else {}

    claude_path = Path.home() / ".claude/settings.json"
    codex_path = Path.home() / ".codex/hooks.json"
    if "claude_backup" not in state:
        state["claude_backup"] = _backup(claude_path)
    if "codex_backup" not in state:
        state["codex_backup"] = _backup(codex_path)

    claude = _read_json(claude_path)
    original_status = claude.get("statusLine")
    if "claude_status_line" not in state:
        state["claude_status_line"] = original_status
    downstream = ""
    if isinstance(original_status, dict):
        command = str(original_status.get("command") or "")
        if not _contains_ours(command):
            downstream = command
        else:
            downstream = str(state.get("statusline_command") or "")
    state["statusline_command"] = downstream
    encoded = base64.urlsafe_b64encode(downstream.encode()).decode()
    claude["statusLine"] = {
        "type": "command",
        "command": f"{command_prefix} statusline-proxy --downstream-b64 {encoded}",
    }
    _merge_hooks(claude, "claude", command_prefix)
    _atomic_json(claude_path, claude)

    codex = _read_json(codex_path)
    _merge_hooks(codex, "codex", command_prefix)
    _atomic_json(codex_path, codex)

    config_path = state_dir / "config.toml"
    if not config_path.exists():
        device = "AUTO" if os.name == "nt" else "/dev/turing-lcd"
        ipc_mode = "tcp" if os.name == "nt" else "unix"
        config_path.write_text(
            "[display]\n"
            f"device = \"{device}\"\n"
            "orientation = \"landscape\"\n"
            "brightness = 25\n"
            "refresh_hz = 2.0\n\n"
            "[dashboard]\n"
            "active_ttl_seconds = 180\n"
            "approval_ttl_seconds = 90\n"
            "idle_title = \"AI WORKBENCH\"\n\n"
            "[ipc]\n"
            f"mode = \"{ipc_mode}\"\n"
            "host = \"127.0.0.1\"\n"
            "port = 45722\n"
        )

    state["command_prefix"] = command_prefix
    if os.name != "nt":
        unit_path = config_home() / "systemd/user/usb-lcd-dashboard.service"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(
            "[Unit]\n"
            "Description=Claude Code and Codex USB LCD dashboard\n"
            "After=graphical-session.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={command_prefix} run\n"
            "Restart=on-failure\n"
            "RestartSec=3\n"
            "NoNewPrivileges=true\n"
            "PrivateTmp=true\n"
            "ProtectSystem=strict\n"
            "ProtectHome=read-only\n"
            f"ReadWritePaths={state_dir} %t\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        state["unit_path"] = str(unit_path)

    _atomic_json(state_path, state)
    print(f"Installed Claude hooks: {claude_path}")
    print(f"Installed Codex hooks:  {codex_path}")
    if os.name == "nt":
        print("Windows login autostart is managed by the USB LCD Dashboard installer.")
    else:
        unit_path = state.get("unit_path", "")
        print(f"Installed user unit:    {unit_path}")
    print("The existing Claude status-line command is preserved behind a proxy.")


def uninstall() -> None:
    state_path = config_home() / "usb-lcd-dashboard/install-state.json"
    state = _read_json(state_path)
    claude_path = Path.home() / ".claude/settings.json"
    codex_path = Path.home() / ".codex/hooks.json"

    claude = _read_json(claude_path)
    for event, groups in list((claude.get("hooks") or {}).items()):
        cleaned = _strip_ours(groups)
        if cleaned:
            claude["hooks"][event] = cleaned
        else:
            claude["hooks"].pop(event, None)
    if "claude_status_line" in state:
        if state["claude_status_line"] is None:
            claude.pop("statusLine", None)
        else:
            claude["statusLine"] = state["claude_status_line"]
    _atomic_json(claude_path, claude)

    codex = _read_json(codex_path)
    for event, groups in list((codex.get("hooks") or {}).items()):
        cleaned = _strip_ours(groups)
        if cleaned:
            codex["hooks"][event] = cleaned
        else:
            codex["hooks"].pop(event, None)
    _atomic_json(codex_path, codex)

    if os.name != "nt":
        default_unit = config_home() / "systemd/user/usb-lcd-dashboard.service"
        unit_path = Path(state.get("unit_path") or default_unit)
        unit_path.unlink(missing_ok=True)
    print("Removed USB LCD hooks and restored the prior Claude status line.")
    print("The dashboard configuration and backups were retained.")
