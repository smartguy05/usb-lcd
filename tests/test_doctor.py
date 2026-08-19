"""`doctor` is the command you run *because* something is wrong, so the one
thing it must never do is fail the way the thing it is diagnosing failed."""

from dataclasses import replace

from usb_lcd_dashboard import doctor
from usb_lcd_dashboard.config import load_config
from usb_lcd_dashboard.doctor import _hook_timeout_ready, checks


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


def test_malformed_hook_timeout_is_reported_not_raised(tmp_path):
    path = tmp_path / "hooks.json"
    path.write_text(
        '{"hooks":{"PreToolUse":[{"hooks":[{"type":"command",'
        '"command":"usb-lcd-dashboard emit","timeout":"soon"}]}]}}',
        encoding="utf-8",
    )
    assert _hook_timeout_ready(path) is False


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


def test_the_turzx_vendor_id_matches_the_driver():
    """doctor repeats the id rather than importing it; pin the two together."""
    from usb_lcd_dashboard.turing_usb import VENDOR_ID

    assert doctor.TURZX_VID == VENDOR_ID


def test_doctor_knows_which_transport_a_config_uses():
    from usb_lcd_dashboard.config import Config

    wide = replace(Config(), display_kind="turing_usb", width=1920, height=462)
    assert doctor._uses_usb_transport(wide)
    assert not doctor._uses_usb_transport(Config())
    # "auto" has to agree with device.make_device, or doctor reports one panel
    # while the daemon opens the other.
    assert doctor._uses_usb_transport(replace(wide, display_kind="auto"))
    assert not doctor._uses_usb_transport(replace(Config(), display_kind="auto"))


def test_doctor_waits_for_the_usb_vendor_not_the_serial_one(monkeypatch):
    """The failure line names the panel you actually have.

    Reporting "waiting for 1a86:5722" at a TURZX panel is what sent a user
    looking for a serial port that was never going to appear.
    """
    from usb_lcd_dashboard.config import Config

    wide = replace(Config(), display_kind="turing_usb", width=1920, height=462)
    monkeypatch.setattr(doctor, "detected_usb_device", lambda config: None)
    monkeypatch.setattr(doctor, "usb_panel_node", lambda config: None)
    device_line = dict((name, detail) for name, _ok, detail in doctor.checks(wide))
    assert "1cbe" in device_line["device"]
    assert "1a86" not in device_line["device"]
