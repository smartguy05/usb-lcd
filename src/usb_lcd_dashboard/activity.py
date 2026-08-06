"""Human-readable descriptions of what an agent is currently doing.

Claude Code builds the line above its spinner ("Editing render.py",
"Running the installer") by asking each tool for a description of its own
input, so the same text can be rebuilt from the tool name and tool input a
hook already delivers.  The phrasing below mirrors the tool definitions in
Claude Code 2.1.223 so the LCD reads the same as the terminal.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


SUMMARY_LIMIT = 50


def _truncate(value: Any, limit: int = SUMMARY_LIMIT) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _short_path(value: Any, cwd: str) -> str:
    """Shorten a path the way Claude Code prints it: relative to the session
    directory when it lives there, otherwise against the home directory."""
    if not value:
        return ""
    raw = str(value)
    if cwd:
        try:
            relative = os.path.relpath(raw, cwd)
        except ValueError:  # different Windows drive
            relative = ""
        if relative and not relative.startswith(".."):
            return _truncate(relative.replace(os.sep, "/"))
    home = str(Path.home())
    if raw.lower().startswith(home.lower() + os.sep):
        return _truncate("~/" + raw[len(home) + 1 :].replace(os.sep, "/"))
    return _truncate(raw.replace(os.sep, "/"))


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    return _truncate(value) if value not in (None, "", [], {}) else ""


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def describe_activity(tool: str, tool_input: Any, cwd: str = "") -> str:
    """Describe a tool call the way the agent's own status line would."""
    if not tool:
        return ""
    fields = tool_input if isinstance(tool_input, dict) else {}
    path = _short_path(_first(fields, "file_path", "notebook_path", "path"), cwd)
    pattern = _text(fields.get("pattern"))
    query = _text(fields.get("query"))
    description = _text(fields.get("description"))
    command = _text(_first(fields, "command", "cmd"))
    url = _text(fields.get("url"))

    if tool == "Read":
        return f"Reading {path}" if path else "Reading file"
    if tool == "Write":
        return f"Writing {path}" if path else "Writing file"
    if tool in {"Edit", "MultiEdit"}:
        return f"Editing {path}" if path else "Editing file"
    if tool == "NotebookEdit":
        return f"Editing notebook {path}" if path else "Editing notebook"
    if tool == "Glob":
        return f"Finding {pattern}" if pattern else "Finding files"
    if tool == "Grep":
        return f"Searching for {pattern}" if pattern else "Searching"
    if tool in {"Bash", "PowerShell"}:
        detail = description or command
        return f"Running {detail}" if detail else "Running command"
    if tool == "WebFetch":
        return f"Fetching {url}" if url else "Fetching web page"
    if tool == "WebSearch":
        return f"Searching for {query}" if query else "Searching the web"
    if tool in {"Task", "Agent"}:
        return description or "Running task"
    if tool == "Monitor":
        return f"Monitoring: {description}" if description else "Monitoring"
    if tool == "Skill":
        return f"Running skill {_text(fields.get('skill'))}".strip() or "Running skill"

    # Unknown tool — Codex tools and MCP servers land here.  Use whatever the
    # input offers rather than falling back to the bare tool name.
    if description:
        return description
    if command:
        return f"Running {command}"
    if url:
        return f"Fetching {url}"
    if pattern or query:
        return f"Searching for {pattern or query}"
    if path:
        return f"Working on {path}"
    return tool
