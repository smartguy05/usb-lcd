import pytest
from PIL import Image

from usb_lcd_dashboard import active_background as ab
from usb_lcd_dashboard.active_background import ActiveBackground, DWELL_SECONDS
from usb_lcd_dashboard.config import ActiveBackgroundConfig


SIZE = (400, 200)


def fixed_speed(px_per_sec):
    return ActiveBackgroundConfig(
        enabled=True, scale=0.5, speed_min=px_per_sec, speed_max=px_per_sec, opacity=1.0
    )


def test_the_shipped_sprites_load():
    frames = ab._load_raw_frames()
    assert frames, "the baked fox run-cycle should ship with the package"
    assert all(f.mode == "RGBA" for f in frames)


def test_step_returns_a_full_panel_overlay_while_the_fox_is_on_screen():
    fox = ActiveBackground(fixed_speed(100))
    # First step enters from just off the left edge; keep stepping until on-screen.
    overlay = None
    for _ in range(60):
        overlay = fox.step(0.2, SIZE)
        if overlay is not None:
            break
    assert overlay is not None
    assert overlay.size == SIZE
    assert overlay.mode == "RGBA"


def test_the_fox_advances_rightward_with_time():
    fox = ActiveBackground(fixed_speed(100))
    fox.step(0.0, SIZE)  # initialise position for the panel size
    start = fox._x
    fox.step(0.5, SIZE)  # 0.5s * 100px/s = 50px
    assert fox._x == pytest.approx(start + 50.0)


def test_the_fox_dwells_off_screen_then_re_enters_from_the_other_side():
    fox = ActiveBackground(fixed_speed(100000))  # cross in a single step
    fox.step(0.0, SIZE)
    exited = fox.step(1.0, SIZE)  # a huge jump pushes it off the right edge
    assert exited is None                 # nothing drawn: it has left the panel
    assert fox._dwell == pytest.approx(DWELL_SECONDS)
    assert fox._x < 0                     # repositioned to re-enter from the left
    # During the dwell it stays hidden.
    assert fox.step(DWELL_SECONDS / 2, SIZE) is None


def test_cpu_load_scales_the_speed(monkeypatch):
    cfg = ActiveBackgroundConfig(enabled=True, scale=0.5, speed_min=10, speed_max=210)
    # 0% CPU -> speed_min.
    monkeypatch.setattr(ab, "_cpu_fraction", lambda: 0.0)
    idle = ActiveBackground(cfg)
    idle.step(0.0, SIZE)
    idle.step(1.0, SIZE)
    slow = idle._x
    # 100% CPU -> speed_max.
    monkeypatch.setattr(ab, "_cpu_fraction", lambda: 1.0)
    busy = ActiveBackground(cfg)
    busy.step(0.0, SIZE)
    busy.step(1.0, SIZE)
    fast = busy._x
    # Same scale, so both foxes start at the same off-screen x; the busier CPU
    # simply carries its fox further in the same second.
    assert fast > slow


def test_missing_sprites_draw_nothing(monkeypatch):
    monkeypatch.setattr(ab, "_load_raw_frames", lambda: [])
    fox = ActiveBackground(fixed_speed(100))
    assert fox.step(0.5, SIZE) is None


def test_opacity_fades_the_layer(monkeypatch):
    monkeypatch.setattr(ab, "_cpu_fraction", lambda: 0.0)
    faded = ActiveBackground(
        ActiveBackgroundConfig(enabled=True, scale=0.5, speed_min=40, speed_max=40, opacity=0.5)
    )
    # Advance until the fox is visible, then check its alpha is at most half.
    overlay = None
    for _ in range(80):
        overlay = faded.step(0.2, SIZE)
        if overlay is not None and overlay.getchannel("A").getextrema()[1] > 0:
            break
    assert overlay is not None
    assert overlay.getchannel("A").getextrema()[1] <= 128


def test_reconfigure_keeps_the_fox_where_it_was():
    fox = ActiveBackground(fixed_speed(100))
    fox.step(0.0, SIZE)
    fox.step(0.5, SIZE)
    where = fox._x
    fox.reconfigure(fixed_speed(300))
    assert fox._x == where
    assert fox.cfg.speed_min == 300
