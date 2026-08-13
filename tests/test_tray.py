"""The tray icon's testable half.

The Win32 half — the window, the message loop, Shell_NotifyIcon — is not
exercised here: it needs a real shell to talk to. What is covered is everything
that decides *what* the icon shows, which is where the behaviour lives.
"""

import os
from dataclasses import replace

import pytest

from usb_lcd_dashboard import tray
from usb_lcd_dashboard.config import Config


def test_menu_offers_the_editor_and_the_way_out():
    items = tray.menu_items(Config(), connected=True)
    commands = [item.command for item in items]
    assert tray.ID_SETTINGS in commands
    assert tray.ID_QUIT in commands


def test_menu_hides_the_editor_when_it_is_not_running():
    """No point offering a link to a server the daemon never started."""
    items = tray.menu_items(replace(Config(), admin_enabled=False), connected=True)
    assert tray.ID_SETTINGS not in [item.command for item in items]
    assert tray.ID_QUIT in [item.command for item in items]


@pytest.mark.parametrize("connected", [True, False])
def test_menu_leads_with_a_disabled_state_row(connected):
    first = tray.menu_items(Config(), connected)[0]
    assert first.command == tray.ID_STATUS
    assert first.enabled is False
    assert ("connected" in first.label) is connected


def test_tooltip_names_the_device_when_attached():
    text = tray.tooltip(True, "COM7")
    assert "COM7" in text and "LCD connected" in text


def test_tooltip_says_so_when_there_is_no_panel():
    text = tray.tooltip(False, "COM7")
    # The configured device is not the attached one, so it is not claimed.
    assert "COM7" not in text and "no LCD" in text


def test_tooltip_fits_the_win32_field():
    """szTip is 128 wide characters including the terminator."""
    assert len(tray.tooltip(True, "C" * 400)) <= 127


@pytest.mark.parametrize("connected", [True, False])
def test_icon_renders_with_transparency(connected):
    image = tray.icon_image(connected, 32)
    assert image.size == (32, 32)
    assert image.mode == "RGBA"
    # The corners are outside the panel, so the taskbar shows through.
    assert image.getpixel((0, 0))[3] == 0


def test_the_two_states_do_not_look_alike():
    live = tray.icon_image(True, 32).tobytes()
    idle = tray.icon_image(False, 32).tobytes()
    assert live != idle


def test_icon_file_carries_every_size(tmp_path):
    from PIL import Image

    path = tray.icon_path(True, tmp_path / "state")
    assert path.exists()
    with Image.open(path) as handle:
        assert set(handle.info["sizes"]) == {(n, n) for n in tray.ICON_SIZES}


def test_icon_states_land_in_separate_files(tmp_path):
    assert tray.icon_path(True, tmp_path) != tray.icon_path(False, tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="Windows has a tray to start")
def test_no_tray_where_there_is_no_tray():
    assert tray.start(Config(), lambda: None) is None
