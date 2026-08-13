"""`doctor` is the command you run *because* something is wrong, so the one
thing it must never do is fail the way the thing it is diagnosing failed."""

from usb_lcd_dashboard.config import load_config
from usb_lcd_dashboard.doctor import checks


BROKEN = """\
[display]
width = 480
height = 320

[[tile]]
widget = "nonesuch"
x = 0
y = 0
w = 480
h = 320
"""

DECORATION_ONLY = """\
[display]
width = 480
height = 320

[[tile]]
widget = "clock"
x = 0
y = 0
w = 480
h = 320
"""


def named(config, name):
    return next((ok, detail) for label, ok, detail in checks(config) if label == name)


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_a_layout_that_will_not_load_is_reported_not_raised(tmp_path):
    config = load_config(write(tmp_path, BROKEN), strict=False)
    ok, detail = named(config, "layout")
    assert ok is False
    # It has to name the offending tile, or the report is no use.
    assert "nonesuch" in detail
    assert "tile[0]" in detail


def test_a_layout_with_no_session_tile_is_still_flagged(tmp_path):
    """The pre-existing check must survive the new one being bolted alongside."""
    config = load_config(write(tmp_path, DECORATION_ONLY), strict=False)
    ok, detail = named(config, "layout")
    assert ok is False
    assert "0 agent slots" in detail


def test_a_good_layout_passes_and_describes_itself(tmp_path):
    config = load_config(tmp_path / "absent.toml", strict=False)
    ok, detail = named(config, "layout")
    assert ok is True
    assert config.layout_error == ""
    assert "480x320" in detail and "1 agent slots" in detail
