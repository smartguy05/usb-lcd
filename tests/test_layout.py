from datetime import datetime, timezone

import pytest
from PIL import Image

from usb_lcd_dashboard import widgets
from usb_lcd_dashboard.background import Background
from usb_lcd_dashboard.layout import Tile, agent_slots, compose, validate
from usb_lcd_dashboard.model import SessionState
from usb_lcd_dashboard.widgets import WidgetSpec
from usb_lcd_dashboard.messaging import MessageSnapshot


NOW = datetime(2026, 8, 6, 14, 37, tzinfo=timezone.utc)
SIZE = (1920, 462)


def solid(color, mode="RGBA"):
    def render(ctx):
        return Image.new(mode, ctx.size, color)

    return render


@pytest.fixture(autouse=True)
def fake_widgets():
    """Register test-only widgets so layout tests do not depend on real ones."""
    added = {
        "red": WidgetSpec(solid("#ff0000")),
        "blue": WidgetSpec(solid("#0000ff")),
        "opaque": WidgetSpec(solid("#00ff00", mode="RGB")),
        "needy": WidgetSpec(lambda ctx: Image.new("RGBA", ctx.size, "#123456"), True),
        "wrongsize": WidgetSpec(lambda ctx: Image.new("RGBA", (7, 7), "#ff00ff")),
        "boom": WidgetSpec(lambda ctx: 1 / 0),
        "slotlabel": WidgetSpec(
            lambda ctx: Image.new("RGBA", ctx.size, (ctx.slot + 1, 0, 0, 255)), True
        ),
    }
    widgets.WIDGETS.update(added)
    yield
    for name in added:
        del widgets.WIDGETS[name]


# ---------------------------------------------------------------- validation

def test_a_valid_layout_passes():
    validate([Tile("red", 0, 0, 100, 100), Tile("blue", 100, 0, 100, 100)], (200, 100))


def test_an_empty_layout_is_rejected():
    with pytest.raises(ValueError, match="at least one tile"):
        validate([], SIZE)


def test_an_unknown_widget_is_rejected_and_lists_the_known_ones():
    with pytest.raises(ValueError, match="not a known widget"):
        validate([Tile("weather", 0, 0, 10, 10)], SIZE)


@pytest.mark.parametrize("w,h", [(0, 10), (10, 0), (-5, 10), (10, -5)])
def test_a_non_positive_size_is_rejected(w, h):
    with pytest.raises(ValueError, match="non-positive size"):
        validate([Tile("red", 0, 0, w, h)], SIZE)


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1)])
def test_a_negative_origin_is_rejected(x, y):
    with pytest.raises(ValueError, match="off screen"):
        validate([Tile("red", x, y, 10, 10)], SIZE)


@pytest.mark.parametrize(
    "tile",
    [
        Tile("red", 1900, 0, 100, 100),   # runs off the right
        Tile("red", 0, 400, 100, 100),    # runs off the bottom
        Tile("red", 0, 0, 1921, 462),
    ],
)
def test_a_tile_that_does_not_fit_is_rejected(tile):
    with pytest.raises(ValueError, match="does not fit"):
        validate([tile], SIZE)


def test_overlapping_tiles_are_rejected_naming_both():
    tiles = [Tile("red", 0, 0, 100, 100), Tile("blue", 50, 50, 100, 100)]
    with pytest.raises(ValueError, match=r"tile\[0\].*overlaps.*tile\[1\]"):
        validate(tiles, SIZE)


def test_a_shared_edge_is_not_an_overlap():
    """Abutting tiles are an ordinary layout, not a mistake."""
    validate([Tile("red", 0, 0, 100, 100), Tile("blue", 100, 0, 100, 100)], (200, 100))
    validate([Tile("red", 0, 0, 100, 100), Tile("blue", 0, 100, 100, 100)], (100, 200))


def test_gaps_are_allowed():
    validate([Tile("red", 12, 12, 100, 100), Tile("blue", 200, 12, 100, 100)], SIZE)


# ---------------------------------------------------------------- agent_slots

def test_agent_slots_counts_only_session_widgets():
    tiles = [
        Tile("red", 0, 0, 10, 10),
        Tile("needy", 10, 0, 10, 10),
        Tile("needy", 20, 0, 10, 10),
    ]
    assert agent_slots(tiles) == 2


def test_only_message_wanting_widgets_receive_the_shared_snapshot():
    seen = []

    def watcher(ctx):
        seen.append(ctx.messages)
        return Image.new("RGBA", ctx.size, "red")

    widgets.WIDGETS["inbox"] = WidgetSpec(watcher, wants_messages=True)
    snapshot = MessageSnapshot(status="connected", unread_conversations=2)
    try:
        compose([Tile("inbox", 0, 0, 20, 10)], (20, 10), now=NOW, messages=snapshot)
    finally:
        del widgets.WIDGETS["inbox"]
    assert seen == [snapshot]
    assert agent_slots([Tile("red", 0, 0, 10, 10)]) == 0


# ---------------------------------------------------------------- composition

def test_composed_frame_matches_the_display_size():
    frame = compose([Tile("red", 12, 12, 100, 100)], SIZE, now=NOW)
    assert frame.size == SIZE
    assert frame.mode == "RGB"


def test_tiles_land_at_their_own_offsets():
    tiles = [Tile("red", 10, 20, 100, 50), Tile("blue", 200, 20, 100, 50)]
    frame = compose(tiles, (400, 100), now=NOW, background=Background(color="#000000"))
    assert frame.getpixel((11, 21)) == (255, 0, 0)
    assert frame.getpixel((201, 21)) == (0, 0, 255)
    # Outside both tiles, and in the gap between them, the background shows.
    assert frame.getpixel((150, 21)) == (0, 0, 0)
    assert frame.getpixel((11, 80)) == (0, 0, 0)
    # A tile does not bleed past its own rect.
    assert frame.getpixel((110, 21)) == (0, 0, 0)


def test_the_background_colour_fills_the_frame():
    frame = compose(
        [Tile("red", 0, 0, 10, 10)], (100, 100),
        now=NOW, background=Background(color="#081018"),
    )
    assert frame.getpixel((50, 50)) == (8, 16, 24)


def test_a_widget_returning_the_wrong_size_is_cropped_not_fatal():
    frame = compose([Tile("wrongsize", 0, 0, 100, 100)], (100, 100), now=NOW)
    assert frame.size == (100, 100)


def test_a_failing_widget_yields_a_fault_tile_and_spares_its_neighbours():
    tiles = [Tile("boom", 0, 0, 200, 100), Tile("red", 200, 0, 200, 100)]
    frame = compose(tiles, (400, 100), now=NOW)
    assert frame.size == (400, 100)
    # The neighbour still rendered.
    assert frame.getpixel((201, 1)) == (255, 0, 0)
    # The fault tile is outlined in the error colour.
    assert frame.getpixel((100, 0)) == (255, 95, 105)


def test_sessions_are_handed_to_session_widgets_in_tile_order():
    tiles = [
        Tile("red", 0, 0, 10, 10),
        Tile("slotlabel", 10, 0, 10, 10),
        Tile("slotlabel", 20, 0, 10, 10),
    ]
    frame = compose(tiles, (30, 10), sessions=[None, None], now=NOW)
    assert frame.getpixel((11, 1))[0] == 1   # slot 0
    assert frame.getpixel((21, 1))[0] == 2   # slot 1


def test_a_session_widget_gets_none_when_there_are_fewer_sessions_than_slots():
    seen = []

    def watcher(ctx):
        seen.append((ctx.slot, ctx.session))
        return Image.new("RGBA", ctx.size, "#000000")

    widgets.WIDGETS["watcher"] = WidgetSpec(watcher, wants_session=True)
    try:
        state = SessionState("claude", "one", NOW, NOW)
        tiles = [Tile("watcher", 0, 0, 10, 10), Tile("watcher", 10, 0, 10, 10)]
        compose(tiles, (20, 10), sessions=[state], now=NOW)
        assert seen == [(0, state), (1, None)]
    finally:
        del widgets.WIDGETS["watcher"]


def test_a_full_screen_rgba_tile_still_composites_over_the_background():
    """The fast path is only for an opaque full-screen tile."""
    frame = compose(
        [Tile("red", 0, 0, 100, 100)], (100, 100),
        now=NOW, background=Background(color="#000000"),
    )
    assert frame.size == (100, 100)
    assert frame.getpixel((50, 50)) == (255, 0, 0)


def test_a_full_screen_opaque_tile_is_returned_directly():
    tile = Tile("opaque", 0, 0, 100, 100)
    frame = compose([tile], (100, 100), now=NOW)
    assert frame.mode == "RGB"
    assert frame.getpixel((50, 50)) == (0, 255, 0)


def test_wallpaper_makes_the_legacy_card_translucent(tmp_path):
    wallpaper = tmp_path / "wallpaper.png"
    Image.new("RGB", (480, 320), "#ff00ff").save(wallpaper)
    frame = compose(
        [Tile("legacy", 0, 0, 480, 320)],
        (480, 320),
        now=NOW,
        background=Background(image=wallpaper, card_opacity=0.5),
    )
    assert frame.mode == "RGB"
    assert frame.getpixel((0, 0)) != (8, 16, 24)
