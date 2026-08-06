from datetime import datetime, timezone

from usb_lcd_dashboard.model import SessionState
from usb_lcd_dashboard.render import render_dashboard, render_idle


NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)


def test_landscape_frames_have_expected_size():
    state = SessionState(
        "codex",
        "session",
        NOW,
        NOW,
        phase="TOOL",
        detail="exec_command",
        activity="Running the Windows installer build",
        model="gpt-5.6-sol",
        cwd="/home/user/project",
        context_percent=64,
        input_tokens=12500,
        output_tokens=2300,
    )
    assert render_dashboard(state, NOW).size == (480, 320)
    assert render_idle("AI WORKBENCH", NOW).size == (480, 320)
