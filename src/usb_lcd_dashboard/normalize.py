from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .activity import describe_activity
from .model import SessionState, utc_now


PHASES = {
    "SessionStart": "READY",
    "UserPromptSubmit": "THINKING",
    "PreToolUse": "TOOL",
    "PermissionRequest": "APPROVAL",
    "PostToolUse": "THINKING",
    "PostToolUseFailure": "ERROR",
    "PermissionDenied": "THINKING",
    "Stop": "DONE",
    "SessionEnd": "ENDED",
    "Notification": "NOTICE",
    "PreCompact": "COMPACTING",
    "PostCompact": "THINKING",
}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _used_percent(used: float | None) -> float | None:
    if used is None:
        return None
    return max(0.0, min(100.0, used))


def _latest_codex_usage(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    transcript = Path(path)
    try:
        with transcript.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 2_000_000))
            raw = handle.read()
    except OSError:
        return {}

    for line in reversed(raw.splitlines()):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        payload = record.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info") or {}
        usage = info.get("last_token_usage") or {}
        window = _number(info.get("model_context_window"))
        total = _number(usage.get("total_tokens"))
        used_percent = total * 100 / window if total is not None and window else None
        return {
            "context_percent": _used_percent(used_percent),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }
    return {}


def normalize_event(
    provider: str,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> SessionState:
    now = now or utc_now()
    event = str(payload.get("hook_event_name") or payload.get("event") or "StatusLine")
    session_id = str(
        payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("turn_id")
        or f"{provider}-status"
    )
    phase = PHASES.get(event, "ACTIVE")
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    detail = tool if phase in {"TOOL", "APPROVAL", "ERROR"} else ""
    if phase == "APPROVAL":
        detail = str(tool_input.get("description") or tool or "User decision needed")
    if event == "StatusLine":
        phase = "ACTIVE"

    workspace = payload.get("workspace") or {}
    model_obj = payload.get("model")
    if isinstance(model_obj, dict):
        model = str(model_obj.get("display_name") or model_obj.get("id") or "")
    else:
        model = str(model_obj or "")

    context = payload.get("context_window") or {}
    context_percent = _number(context.get("used_percentage"))
    if context_percent is None:
        remaining = _number(context.get("remaining_percentage"))
        context_percent = (
            _used_percent(100.0 - remaining) if remaining is not None else None
        )
    input_tokens = context.get("total_input_tokens")
    output_tokens = context.get("total_output_tokens")
    cost = payload.get("cost") or {}
    usage = _latest_codex_usage(payload.get("transcript_path")) if provider == "codex" else {}

    cwd = str(
        workspace.get("current_dir")
        or payload.get("cwd")
        or workspace.get("project_dir")
        or ""
    )

    return SessionState(
        provider=provider,
        session_id=session_id,
        updated_at=now,
        started_at=now,
        phase=phase,
        detail=detail,
        activity=describe_activity(tool, tool_input, cwd),
        model=model,
        cwd=cwd,
        permission_mode=str(payload.get("permission_mode") or ""),
        context_percent=context_percent
        if context_percent is not None
        else usage.get("context_percent"),
        input_tokens=input_tokens
        if input_tokens is not None
        else usage.get("input_tokens"),
        output_tokens=output_tokens
        if output_tokens is not None
        else usage.get("output_tokens"),
        cost_usd=_number(cost.get("total_cost_usd")),
        ended=phase == "ENDED",
        extra={"event": event},
    )

