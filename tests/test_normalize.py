import json
from datetime import datetime, timezone

from usb_lcd_dashboard.model import StateStore
from usb_lcd_dashboard.normalize import normalize_event


NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)


def test_claude_statusline_fields():
    state = normalize_event(
        "claude",
        {
            "session_id": "abc",
            "model": {"display_name": "Opus"},
            "workspace": {"current_dir": "/work/widget"},
            "context_window": {
                "used_percentage": 42.5,
                "total_input_tokens": 1234,
                "total_output_tokens": 99,
            },
            "cost": {"total_cost_usd": 1.25},
        },
        NOW,
    )
    assert state.phase == "ACTIVE"
    assert state.project == "widget"
    assert state.model == "Opus"
    assert state.context_percent == 42.5
    assert state.cost_usd == 1.25


def test_claude_remaining_percentage_is_converted_to_used():
    state = normalize_event(
        "claude",
        {
            "context_window": {
                "remaining_percentage": 93,
            },
        },
        NOW,
    )
    assert state.context_percent == 7


def test_codex_context_is_reported_as_used(tmp_path):
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 258400,
                        "last_token_usage": {
                            "input_tokens": 16725,
                            "output_tokens": 118,
                            "total_tokens": 16843,
                        },
                    },
                }
            }
        )
        + "\n"
    )
    state = normalize_event(
        "codex",
        {"transcript_path": str(transcript)},
        NOW,
    )
    assert state.context_percent == 16843 * 100 / 258400
    assert state.input_tokens == 16725
    assert state.output_tokens == 118


def test_tool_and_approval_events():
    tool = normalize_event(
        "codex",
        {
            "session_id": "a",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
        },
        NOW,
    )
    approval = normalize_event(
        "codex",
        {
            "session_id": "a",
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"description": "Install device rule"},
        },
        NOW,
    )
    assert (tool.phase, tool.detail) == ("TOOL", "Bash")
    assert (approval.phase, approval.detail) == ("APPROVAL", "Install device rule")


def test_activity_replaces_the_tool_name_for_the_headline():
    state = normalize_event(
        "claude",
        {
            "session_id": "a",
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/work/widget/src/render.py"},
            "cwd": "/work/widget",
        },
        NOW,
    )
    assert state.activity == "Editing src/render.py"


def test_activity_is_cleared_when_an_event_carries_no_tool():
    store = StateStore()
    store.apply(
        normalize_event(
            "claude",
            {
                "session_id": "a",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"description": "Build the installer"},
            },
            NOW,
        )
    )
    working = store.apply(
        normalize_event(
            "claude",
            {"session_id": "a", "hook_event_name": "PostToolUse", "tool_name": "Bash",
             "tool_input": {"description": "Build the installer"}},
            NOW,
        )
    )
    prompt = store.apply(
        normalize_event(
            "claude",
            {"session_id": "a", "hook_event_name": "UserPromptSubmit"},
            NOW,
        )
    )
    assert working.activity == "Running Build the installer"
    assert prompt.activity == ""


def test_statusline_keeps_the_activity_from_the_last_hook():
    store = StateStore()
    store.apply(
        normalize_event(
            "claude",
            {
                "session_id": "a",
                "hook_event_name": "PreToolUse",
                "tool_name": "Grep",
                "tool_input": {"pattern": "render_dashboard"},
            },
            NOW,
        )
    )
    status = store.apply(
        normalize_event("claude", {"session_id": "a", "model": "Opus"}, NOW)
    )
    assert status.activity == "Searching for render_dashboard"


def test_session_end_is_not_active():
    state = normalize_event(
        "claude",
        {"session_id": "a", "hook_event_name": "SessionEnd"},
        NOW,
    )
    assert state.ended

