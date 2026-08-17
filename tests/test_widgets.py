from datetime import datetime, timedelta, timezone

import pytest
from PIL import ImageChops

from usb_lcd_dashboard.layout import TileContext
from usb_lcd_dashboard.model import SessionState
from usb_lcd_dashboard.messaging import MessageItem, MessageSnapshot
from usb_lcd_dashboard.widgets import WIDGETS
from usb_lcd_dashboard.widgets.agent import render_agent
from usb_lcd_dashboard.widgets.base import panel_fill
from usb_lcd_dashboard.widgets.clock import render_clock
from usb_lcd_dashboard.widgets.messages import render_messages
from usb_lcd_dashboard.widgets.notifications import render_notifications
from usb_lcd_dashboard.widgets.todos import render_todos
from usb_lcd_dashboard.notifications import NotificationItem, NotificationSnapshot
from usb_lcd_dashboard.todos import TodoItem, TodoSnapshot


NOW = datetime(2026, 8, 6, 14, 37, 5, tzinfo=timezone.utc)

# A wide column on the ultra-wide, a square tile, the legacy panel, and a
# deliberately cramped strip that nothing is tuned for.
SIZES = [(486, 438), (438, 438), (480, 320), (300, 120), (120, 90)]


def context(size, **kwargs):
    options = kwargs.pop("options", {})
    return TileContext(size=size, now=NOW, options=options, **kwargs)


def differs(a, b):
    """Pillow's getbbox() looks only at alpha by default, and these tiles are
    RGBA with identical alpha — so colour differences need alpha_only=False."""
    return ImageChops.difference(a, b).getbbox(alpha_only=False) is not None


def full_session(**kwargs):
    defaults = dict(
        provider="claude",
        session_id="one",
        updated_at=NOW,
        started_at=NOW - timedelta(minutes=7, seconds=12),
        phase="TOOL",
        activity="Editing src/usb_lcd_dashboard/widgets/agent.py",
        model="Claude Opus 5 (1M context)",
        cwd="/work/usb-lcd",
        context_percent=63.4,
        input_tokens=128_000,
        output_tokens=9_100,
        cost_usd=1.23,
    )
    return SessionState(**{**defaults, **kwargs})


# ------------------------------------------------------------------- registry

def test_the_registry_exposes_the_expected_widgets():
    assert set(WIDGETS) == {"agent", "clock", "crab", "legacy", "messages", "notifications", "todos"}
    assert WIDGETS["agent"].wants_session is True
    assert WIDGETS["crab"].wants_session is True
    assert WIDGETS["clock"].wants_session is False
    assert WIDGETS["messages"].wants_messages is True
    assert WIDGETS["notifications"].wants_notifications is True
    assert WIDGETS["todos"].wants_todos is True


# ---------------------------------------------------------------------- todos

@pytest.mark.parametrize("size", SIZES)
def test_the_todo_widget_renders_empty_and_populated_at_every_size(size):
    empty = render_todos(context(size, todos=TodoSnapshot()))
    item = TodoItem("a", "Call the dentist", "", "high", "2026-08-17", "open", 0,
                    NOW.isoformat(), NOW.isoformat(), None)
    populated = render_todos(context(size, todos=TodoSnapshot((item,), NOW.isoformat())))
    assert empty.size == populated.size == size
    assert empty.mode == populated.mode == "RGBA"
    assert differs(empty, populated)


def test_todo_pages_rotate_deterministically():
    items = tuple(
        TodoItem(str(i), f"Todo {i}", "", "normal", None, "open", i,
                 NOW.isoformat(), NOW.isoformat(), None)
        for i in range(12)
    )
    snapshot = TodoSnapshot(items, NOW.isoformat())
    first = render_todos(context((240, 100), todos=snapshot, options={"rotation_seconds": 8}))
    later = render_todos(TileContext((240, 100), NOW + timedelta(seconds=8), {"rotation_seconds": 8}, todos=snapshot))
    assert differs(first, later)


# ------------------------------------------------------------- notifications

@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("status", ["unsupported", "permission_required", "denied", "connecting", "error"])
def test_every_empty_notification_state_fills_its_tile(size, status):
    image = render_notifications(context(size, notifications=NotificationSnapshot(status=status)))
    assert image.size == size
    assert image.mode == "RGBA"


def test_notifications_rotate_at_the_configured_interval():
    items = tuple(
        NotificationItem(index, f"app.{index}", f"App {index}", f"Title {index}", "Body", NOW)
        for index in range(2)
    )
    snapshot = NotificationSnapshot(status="connected", items=items, updated_at=NOW, changed_at=NOW)
    first = render_notifications(context((300, 180), notifications=snapshot, options={"rotation_seconds": 8}))
    later = render_notifications(TileContext((300, 180), NOW + timedelta(seconds=8), {"rotation_seconds": 8}, notifications=snapshot))
    assert differs(first, later)


# ------------------------------------------------------------------- messages

@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("status", ["unconfigured", "disconnected", "connecting", "error"])
def test_every_empty_messages_state_fills_its_tile(size, status):
    image = render_messages(context(size, messages=MessageSnapshot(status=status)))
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize("size", SIZES)
def test_the_latest_message_renders_at_every_size(size):
    snapshot = MessageSnapshot(
        status="connected",
        latest=MessageItem(
            provider="discord",
            conversation="Project launch",
            sender="Alex",
            preview="Can you review this pull request before the meeting?",
            created_at=NOW - timedelta(minutes=2),
        ),
        unread_conversations=3,
        updated_at=NOW,
    )
    image = render_messages(context(size, messages=snapshot))
    assert image.size == size



# ---------------------------------------------------------------------- clock

@pytest.mark.parametrize("size", SIZES)
def test_the_clock_fills_exactly_its_tile(size):
    image = render_clock(context(size))
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"hour12": False},
        {"seconds": True},
        {"show_date": False},
        {"title": "HOME", "seconds": True, "hour12": False},
        {"background": "transparent"},
        {"background": "#101c28", "opacity": 0.5},
    ],
)
def test_the_clock_renders_every_option_combination(options):
    image = render_clock(context((404, 438), options=options))
    assert image.size == (404, 438)


def test_the_clock_shows_a_different_minute_after_a_minute():
    first = render_clock(context((404, 438)))
    later = TileContext(
        size=(404, 438), now=NOW + timedelta(minutes=1), options={}
    )
    assert differs(first, render_clock(later))


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("options", [{"seconds": True}, {"seconds": False}])
def test_the_clock_never_paints_over_the_edge_of_its_tile(size, options):
    """The seconds token used to be sized independently of the time, so a big
    clock pushed it off the right edge and it came out clipped."""
    width, height = size
    image = render_clock(context(size, options={**options, "background": "transparent"}))
    painted = image.getbbox(alpha_only=False)
    assert painted is not None, "the clock drew nothing at all"
    left, top, right, bottom = painted
    assert left >= 0 and top >= 0 and right <= width and bottom <= height
    # Nothing should be touching the very edge, where it would look cut off.
    assert right < width and left > 0


def test_a_transparent_tile_leaves_the_backdrop_unpainted():
    image = render_clock(context((404, 438), options={"background": "transparent"}))
    assert image.getpixel((2, 2))[3] == 0


def test_an_opaque_tile_paints_its_card():
    image = render_clock(context((404, 438), options={"background": "#101c28"}))
    assert image.getpixel((202, 220))[3] == 255


def test_opacity_is_applied_to_the_card():
    image = render_clock(
        context((404, 438), options={"background": "#101c28", "opacity": 0.5})
    )
    assert image.getpixel((202, 20))[3] == 128


@pytest.mark.parametrize(
    "options,expected",
    [
        ({}, (16, 28, 40, 255)),
        ({"opacity": 0.0}, (16, 28, 40, 0)),
        ({"background": "#ff0000", "opacity": 0.25}, (255, 0, 0, 64)),
        ({"background": "transparent"}, None),
        ({"background": None}, None),
        ({"background": "#ff0000", "opacity": "nonsense"}, (255, 0, 0, 255)),
    ],
)
def test_panel_fill_resolves_the_tile_backdrop(options, expected):
    assert panel_fill(options) == expected


# ---------------------------------------------------------------------- agent

@pytest.mark.parametrize("size", SIZES)
def test_the_agent_card_fills_exactly_its_tile(size):
    image = render_agent(context(size, session=full_session(), slot=0))
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize("size", SIZES)
def test_an_empty_slot_fills_exactly_its_tile(size):
    assert render_agent(context(size, session=None, slot=1)).size == size


@pytest.mark.parametrize("size", SIZES)
def test_a_session_with_nothing_filled_in_still_renders(size):
    """Every optional field is empty or None the moment a session starts."""
    bare = SessionState("codex", "bare", NOW, NOW)
    assert render_agent(context(size, session=bare, slot=0)).size == size


@pytest.mark.parametrize(
    "phase,detail",
    [
        ("TOOL", ""),
        ("THINKING", ""),
        ("ACTIVE", ""),
        ("APPROVAL", "Bash(rm -rf build) wants to run"),
        ("ERROR", "tool call failed"),
        ("DONE", ""),
        ("READY", ""),
    ],
)
def test_every_phase_renders_at_a_wide_tile(phase, detail):
    state = full_session(phase=phase, detail=detail)
    assert render_agent(context((486, 438), session=state, slot=0)).size == (486, 438)


def test_each_provider_gets_its_own_accent():
    a = render_agent(context((486, 438), session=full_session(provider="claude"), slot=0))
    b = render_agent(context((486, 438), session=full_session(provider="codex"), slot=0))
    assert differs(a, b)


@pytest.mark.parametrize("percent", [None, 0, 0.4, 50, 99.9, 100])
def test_the_context_bar_copes_with_every_percentage(percent):
    state = full_session(context_percent=percent)
    assert render_agent(context((486, 438), session=state, slot=0)).size == (486, 438)


def test_a_very_long_activity_line_still_fits():
    state = full_session(
        activity="Running the windows installer build inside the podman container "
        "for the packaging target with a very long description indeed"
    )
    assert render_agent(context((486, 438), session=state, slot=0)).size == (486, 438)


def test_the_empty_slot_says_which_slot_it_is():
    first = render_agent(context((486, 438), session=None, slot=0))
    second = render_agent(context((486, 438), session=None, slot=1))
    assert differs(first, second)


def test_a_disconnected_panel_is_reported_on_an_empty_slot():
    connected = render_agent(context((486, 438), session=None, slot=0, connected=True))
    waiting = render_agent(context((486, 438), session=None, slot=0, connected=False))
    assert differs(connected, waiting)
