"""The tray icon's testable half.

The Win32 half — the window, the message loop, Shell_NotifyIcon — is not
exercised here: it needs a real shell to talk to. What is covered is everything
that decides *what* the icon shows, which is where the behaviour lives.
"""

import os
from dataclasses import replace
from pathlib import Path

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
def test_no_tray_without_a_graphical_session(monkeypatch):
    """A headless box gets no icon and no complaint."""
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert tray.start(Config(), lambda: None) is None


@pytest.mark.skipif(os.name == "nt", reason="Linux typelibs")
def test_no_tray_without_the_typelib(monkeypatch):
    """A desktop session missing the GI typelib degrades instead of raising.

    start() must not propagate: the daemon treats a tray failure as survivable,
    and this is the path a Debian install with the Recommends declined takes.
    """
    from usb_lcd_dashboard import tray_linux

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        tray_linux, "_import_gi", lambda: (_ for _ in ()).throw(ImportError("no gi"))
    )
    assert tray.start(Config(), lambda: None) is None


@pytest.mark.skipif(os.name == "nt", reason="Linux typelibs")
def test_the_tray_reports_a_missing_typelib_as_actionable(monkeypatch):
    from usb_lcd_dashboard import tray_linux

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        tray_linux,
        "_import_gi",
        lambda: (_ for _ in ()).throw(ValueError("Namespace X not available")),
    )
    available, reason = tray_linux.tray_host_available()
    assert not available
    assert "gir1.2-ayatanaappindicator3-0.1" in reason


@pytest.mark.skipif(os.name == "nt", reason="Linux writes PNGs, Windows .ico")
def test_the_linux_icon_states_land_in_separate_png_files(tmp_path):
    live = tray.icon_png_path(True, tmp_path)
    idle = tray.icon_png_path(False, tmp_path)
    assert live != idle
    assert live.suffix == ".png" and live.exists() and idle.exists()
    # The name is what an SNI host resolves against the theme path, so the
    # basename has to carry the state rather than the directory.
    assert live.stem.startswith(tray.ICON_THEME_NAME)


@pytest.mark.skipif(os.name == "nt", reason="Linux tray internals")
def test_the_linux_tray_marshals_onto_the_default_main_context():
    """_post must use GLib.idle_add, i.e. the *global default* context.

    Regression pin, and an expensive one. A private thread-default MainContext
    looks tidier and is wrong: libdbusmenu-gtk activates the clicked GtkMenuItem
    from a g_idle_add hardcoded to the default context, so on any other context
    the D-Bus Event call still succeeds, the menu still renders correctly, and
    no menu item ever fires. There is no error to go on — only silence.
    """
    from usb_lcd_dashboard.tray_linux import LinuxTrayIcon

    class FakeGLib:
        def __init__(self):
            self.idle_added = []

        def idle_add(self, func):
            self.idle_added.append(func)

    icon = LinuxTrayIcon(Config(), lambda: None, Path("/nonexistent"))
    fake = FakeGLib()
    icon._glib = fake
    sentinel = object()
    icon._post(sentinel)
    assert fake.idle_added == [sentinel]


@pytest.mark.skipif(os.name == "nt", reason="Linux tray internals")
def test_the_linux_tray_drops_work_before_its_loop_exists():
    """set_connected can arrive from the daemon before the thread is up."""
    from usb_lcd_dashboard.tray_linux import LinuxTrayIcon

    icon = LinuxTrayIcon(Config(), lambda: None, Path("/nonexistent"))
    icon._post(object())  # must not raise with _glib still None


@pytest.mark.skipif(os.name == "nt", reason="Linux desktop integration")
def test_opening_a_uri_tries_the_portal_first(monkeypatch):
    """Portal before xdg-open, because it is the only one that works sandboxed.

    Measured, not assumed: inside the unit's sandbox both plain xdg-open and
    `systemd-run -- xdg-open` exit 0 and open nothing, while the portal opens
    the tab. Reordering this silently breaks the menu on a normal install, and
    the exit codes will not tell you.
    """
    calls = []
    monkeypatch.setattr(tray, "_open_via_portal", lambda uri: calls.append(uri))
    monkeypatch.setattr(
        tray.subprocess, "run",
        lambda *a, **k: pytest.fail("xdg-open ran even though the portal worked"),
    )
    tray._open_in_desktop("http://127.0.0.1:45723/")
    assert calls == ["http://127.0.0.1:45723/"]


@pytest.mark.skipif(os.name == "nt", reason="Linux desktop integration")
def test_opening_a_uri_falls_back_when_there_is_no_portal(monkeypatch):
    """A desktop with no portal, or a daemon run from a shell, still works."""
    def no_portal(uri):
        raise RuntimeError("no portal here")

    ran = []

    class Result:
        returncode = 0

    monkeypatch.setattr(tray, "_open_via_portal", no_portal)
    monkeypatch.setattr(tray.shutil, "which", lambda name: "/usr/bin/xdg-open")
    monkeypatch.setattr(tray.subprocess, "run", lambda *a, **k: ran.append(a[0]) or Result())
    tray._open_in_desktop("http://127.0.0.1:45723/")
    assert ran and ran[0][0] == "/usr/bin/xdg-open"
