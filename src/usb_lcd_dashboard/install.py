from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import config_home, default_config_toml


COMMON_EVENTS = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    # Fires when the agent needs permission or has been waiting at a prompt,
    # which is the "your attention is needed" signal the crab widget alarms on.
    # Without it the NOTICE phase is mapped but unreachable.
    "Notification",
    "Stop",
    "SessionEnd",
]
EVENTS_BY_PROVIDER = {
    "claude": [*COMMON_EVENTS, "PostToolUseFailure"],
    "codex": COMMON_EVENTS,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
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
        if os.name == "nt":
            # Claude Code launches hooks through Bash even on Windows.  An
            # unquoted ``C:\\...`` command is parsed as escapes and collapses
            # into ``C:Users...``.  Git Bash accepts a quoted C:/ path and
            # Windows also accepts forward slashes.
            return f'"{script.as_posix()}"'
        return _quote_command([str(script)])
    return _quote_command([_hook_interpreter(), "-m", "usb_lcd_dashboard"])


def _mcp_command(explicit: str | None = None) -> tuple[str, list[str]]:
    if explicit:
        return explicit, ["mcp"]
    executable_name = "usb-lcd-dashboard.exe" if os.name == "nt" else "usb-lcd-dashboard"
    script = Path(sys.executable).with_name(executable_name)
    if script.exists():
        return str(script), ["mcp"]
    # MCP is stdio: unlike hooks it must use console python.exe on Windows so
    # the client can attach pipes. pythonw.exe deliberately has no stdio.
    interpreter = Path(sys.executable)
    if os.name == "nt" and interpreter.name.casefold() == "pythonw.exe":
        interpreter = interpreter.with_name("python.exe")
    return str(interpreter), ["-m", "usb_lcd_dashboard", "mcp"]


MCP_NAME = "usb-lcd-dashboard-todos"
_CODEX_MCP_HEADER = f"[mcp_servers.{MCP_NAME}]"
_CODEX_MCP_PATTERN = re.compile(
    rf"(?ms)^\[mcp_servers\.(?:{re.escape(MCP_NAME)}|\"{re.escape(MCP_NAME)}\")\]\s*\n.*?(?=^\[|\Z)"
)


def _codex_mcp_section(command: str, args: list[str]) -> str:
    return (
        f"{_CODEX_MCP_HEADER}\n"
        f"command = {json.dumps(command)}\n"
        f"args = {json.dumps(args)}\n"
    )


def _replace_codex_mcp(text: str, replacement: str | None) -> tuple[str, str | None]:
    match = _CODEX_MCP_PATTERN.search(text)
    previous = match.group(0).rstrip() if match else None
    without = _CODEX_MCP_PATTERN.sub("", text).rstrip()
    if replacement:
        without = f"{without}\n\n{replacement.strip()}" if without else replacement.strip()
    return without.rstrip() + "\n", previous


def _hook_interpreter() -> str:
    """Interpreter for hook commands.

    Hooks fire on every tool call, so on Windows they must run under the
    console-less pythonw.exe; python.exe flashes a terminal window each time.
    """
    if os.name != "nt":
        return sys.executable
    windowless = Path(sys.executable).with_name("pythonw.exe")
    return str(windowless) if windowless.exists() else sys.executable


UNIT_NAME = "usb-lcd-dashboard.service"


def _systemctl(*args: str) -> bool:
    """Run `systemctl --user`, reporting whether it worked.

    Never fatal. There is no user manager to talk to inside a container, a
    chroot, or a Docker build, and a package that fails to install because it
    could not start a service in a build sandbox would be worse than one that
    installs and needs starting by hand.
    """
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return False
    try:
        result = subprocess.run(
            [systemctl, "--user", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _systemd_enable() -> bool:
    """Load the new unit and start it, the way the Windows installer starts the app.

    Writing the unit file and leaving it is a half-installed state: the panel
    stays dark until the user finds the three systemctl commands in the README.
    """
    if not _systemctl("daemon-reload"):
        return False
    return _systemctl("enable", "--now", UNIT_NAME)


def _systemd_disable() -> None:
    """Stop and unwire the unit before its file is deleted.

    Order matters: deleting the unit first leaves a dangling symlink in
    default.target.wants and leaves the daemon running with the panel held open.
    """
    _systemctl("disable", "--now", UNIT_NAME)


def _merge_hooks(settings: dict[str, Any], provider: str, command_prefix: str) -> None:
    hooks = settings.setdefault("hooks", {})
    # These hooks only report optional display telemetry. A missing daemon,
    # damaged local config, or transient interpreter failure must never turn an
    # otherwise successful agent event into a hook failure. Claude uses Bash on
    # Windows, while Codex uses Windows PowerShell: a quoted executable needs
    # PowerShell's call operator and PowerShell 5.1 cannot parse ``||``.
    if provider == "codex" and os.name == "nt":
        command = f"& {command_prefix} emit --provider {provider}; exit 0"
    else:
        command = f"{command_prefix} emit --provider {provider} || exit 0"
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
                        "timeout": 10,
                    }
                ]
            }
        )
        hooks[event] = groups


def install(executable: str | None = None) -> None:
    command_prefix = _command_prefix(executable)
    mcp_command, mcp_args = _mcp_command(executable)
    state_dir = config_home() / "usb-lcd-dashboard"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "install-state.json"
    state = _read_json(state_path) if state_path.exists() else {}

    claude_path = Path.home() / ".claude/settings.json"
    codex_path = Path.home() / ".codex/hooks.json"
    claude_user_path = Path.home() / ".claude.json"
    codex_config_path = Path.home() / ".codex/config.toml"
    if "claude_backup" not in state:
        state["claude_backup"] = _backup(claude_path)
    if "codex_backup" not in state:
        state["codex_backup"] = _backup(codex_path)
    if "claude_user_backup" not in state:
        state["claude_user_backup"] = _backup(claude_user_path)
    if "codex_config_backup" not in state:
        state["codex_config_backup"] = _backup(codex_config_path)

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

    claude_user = _read_json(claude_user_path)
    claude_servers = claude_user.setdefault("mcpServers", {})
    if not isinstance(claude_servers, dict):
        raise ValueError("~/.claude.json mcpServers must be an object")
    if "claude_todo_mcp_previous" not in state:
        state["claude_todo_mcp_previous"] = claude_servers.get(MCP_NAME)
        state["claude_todo_mcp_had_previous"] = MCP_NAME in claude_servers
    claude_servers[MCP_NAME] = {
        "type": "stdio", "command": mcp_command, "args": mcp_args, "env": {}
    }
    _atomic_json(claude_user_path, claude_user)

    try:
        codex_text = codex_config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        codex_text = ""
    codex_updated, previous_section = _replace_codex_mcp(
        codex_text, _codex_mcp_section(mcp_command, mcp_args)
    )
    if "codex_todo_mcp_previous" not in state:
        state["codex_todo_mcp_previous"] = previous_section
    _atomic_text(codex_config_path, codex_updated)

    config_path = state_dir / "config.toml"
    if not config_path.exists():
        device = "AUTO" if os.name == "nt" else "/dev/turing-lcd"
        ipc_mode = "tcp" if os.name == "nt" else "unix"
        config_path.write_text(default_config_toml(device, ipc_mode), encoding="utf-8")

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
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        state["unit_path"] = str(unit_path)
        state["unit_started"] = _systemd_enable()

    _atomic_json(state_path, state)
    print(f"Installed Claude hooks: {claude_path}")
    print(f"Installed Codex hooks:  {codex_path}")
    if os.name == "nt":
        print("Windows login autostart is managed by the USB LCD Dashboard installer.")
    else:
        unit_path = state.get("unit_path", "")
        print(f"Installed user unit:    {unit_path}")
        if state.get("unit_started"):
            print("Started the dashboard:  systemctl --user status usb-lcd-dashboard")
        else:
            # A build sandbox or a chroot has no user manager. Say so plainly
            # rather than leaving the panel dark with no explanation.
            print("Could not start it here; once logged in, run:")
            print("  systemctl --user daemon-reload")
            print("  systemctl --user enable --now usb-lcd-dashboard")
    print("The existing Claude status-line command is preserved behind a proxy.")
    print("Installed human-todo MCP tools for Claude Code and Codex.")


def uninstall() -> None:
    state_path = config_home() / "usb-lcd-dashboard/install-state.json"
    state = _read_json(state_path)
    claude_path = Path.home() / ".claude/settings.json"
    codex_path = Path.home() / ".codex/hooks.json"
    claude_user_path = Path.home() / ".claude.json"
    codex_config_path = Path.home() / ".codex/config.toml"

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

    claude_user = _read_json(claude_user_path)
    servers = claude_user.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("~/.claude.json mcpServers must be an object")
    if state.get("claude_todo_mcp_had_previous"):
        servers[MCP_NAME] = state.get("claude_todo_mcp_previous")
    else:
        servers.pop(MCP_NAME, None)
    if not servers:
        claude_user.pop("mcpServers", None)
    _atomic_json(claude_user_path, claude_user)

    try:
        codex_text = codex_config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        codex_text = ""
    restored, _current = _replace_codex_mcp(
        codex_text, state.get("codex_todo_mcp_previous")
    )
    _atomic_text(codex_config_path, restored)

    if os.name != "nt":
        default_unit = config_home() / f"systemd/user/{UNIT_NAME}"
        unit_path = Path(state.get("unit_path") or default_unit)
        # Before the file goes, not after.
        _systemd_disable()
        unit_path.unlink(missing_ok=True)
        _systemctl("daemon-reload")
    print("Removed USB LCD hooks and restored the prior Claude status line.")
    print("The dashboard configuration and backups were retained.")
    print("Removed the human-todo MCP tools; todo history was retained.")
