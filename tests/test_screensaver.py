from datetime import datetime, timedelta, timezone

from PIL import ImageChops

from usb_lcd_dashboard.screensaver import render_screensaver


NOW = datetime(2026, 8, 17, 12, 0, 10, tzinfo=timezone.utc)


def test_screensaver_is_stable_within_a_minute():
    first = render_screensaver((480, 320), NOW)
    later = render_screensaver((480, 320), NOW + timedelta(seconds=40))
    assert ImageChops.difference(first, later).getbbox() is None


def test_screensaver_clock_moves_each_minute_on_black():
    first = render_screensaver((480, 320), NOW)
    later = render_screensaver((480, 320), NOW + timedelta(minutes=1))
    assert ImageChops.difference(first, later).getbbox() is not None
    assert first.getpixel((0, 0)) == (0, 0, 0)
