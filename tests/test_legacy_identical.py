"""The gate on "the 3.5" panel keeps working exactly as it does today".

Not a golden file: it renders both ways in the same process and asserts the
pixels are the same, so it keeps holding as the layout system grows.
"""

from datetime import datetime, timezone

from PIL import ImageChops

from usb_lcd_dashboard.layout import Tile, compose
from usb_lcd_dashboard.model import SessionState
from usb_lcd_dashboard.render import (
    LEGACY_HEIGHT,
    LEGACY_WIDTH,
    render_dashboard,
    render_idle,
)


NOW = datetime(2026, 8, 6, 14, 37, tzinfo=timezone.utc)
SIZE = (LEGACY_WIDTH, LEGACY_HEIGHT)
FULL_SCREEN = [Tile("legacy", 0, 0, LEGACY_WIDTH, LEGACY_HEIGHT)]


def session(**kwargs):
    defaults = dict(
        provider="claude",
        session_id="one",
        updated_at=NOW,
        started_at=NOW,
        cwd="/work/demo",
        model="Claude Opus 5",
        context_percent=63.4,
        input_tokens=128_000,
        output_tokens=9_100,
        cost_usd=1.23,
    )
    return SessionState(**{**defaults, **kwargs})


def identical(a, b):
    return a.size == b.size and ImageChops.difference(a, b).getbbox() is None


CASES = [
    session(phase="TOOL", activity="Editing src/usb_lcd_dashboard/layout.py"),
    session(phase="THINKING"),
    session(phase="APPROVAL", detail="Bash(rm -rf build) wants to run"),
    session(phase="ERROR", detail="tool call failed"),
    session(phase="ACTIVE", activity="Running the installer build for windows packaging"),
    session(phase="DONE"),
    session(provider="codex", phase="TOOL", activity="Searching for render_dashboard"),
    SessionState("claude", "bare", NOW, NOW),
]


def test_composed_dashboard_is_pixel_identical():
    for state in CASES:
        composed = compose(FULL_SCREEN, SIZE, sessions=[state], now=NOW)
        assert identical(composed, render_dashboard(state, NOW)), state.phase


def test_composed_idle_is_pixel_identical():
    for connected in (True, False):
        composed = compose(
            FULL_SCREEN, SIZE, sessions=[None], now=NOW,
            connected=connected, idle_title="AI WORKBENCH",
        )
        assert identical(composed, render_idle("AI WORKBENCH", NOW, connected))


def test_full_screen_tile_is_handed_back_untouched():
    """Not merely equal — the same object, so no copy can perturb it."""
    state = CASES[0]
    expected = render_dashboard(state, NOW)
    composed = compose(FULL_SCREEN, SIZE, sessions=[state], now=NOW)
    assert composed.mode == "RGB"
    assert identical(composed, expected)
    # A background is irrelevant to the fast path: the tile covers everything.
    from usb_lcd_dashboard.background import Background

    with_bg = compose(
        FULL_SCREEN, SIZE, sessions=[state], now=NOW,
        background=Background(color="#ff0000"),
    )
    assert identical(with_bg, expected)


def test_a_tile_option_can_override_the_idle_title():
    tiles = [Tile("legacy", 0, 0, LEGACY_WIDTH, LEGACY_HEIGHT, {"title": "HOME"})]
    composed = compose(tiles, SIZE, sessions=[None], now=NOW, idle_title="AI WORKBENCH")
    assert identical(composed, render_idle("HOME", NOW, True))
