"""The Linux notification-area icon, the counterpart to tray.py's Win32 one.

Same bargain as on Windows: under a systemd user unit the daemon has no window
and no console, so when the panel is unplugged — or, on this desk, handed to
another machine by a KVM — the icon is the only evidence it is alive, and its
menu is the way into the settings editor and the stop button.

AyatanaAppIndicator3 through PyGObject rather than a hand-rolled
StatusNotifierItem: both halves are ordinary Ubuntu archive packages, which is
the same rule the .deb already follows for Pillow and pyserial, and it keeps the
com.canonical.dbusmenu surface out of this repo. It is the reason this lives in
its own module — tray.py stays importable on a machine with no GTK at all, and
the portable half (menu_items, icon_image, tooltip, open_*) is shared, so the
two platforms cannot drift apart in what the menu says.

GTK is not thread-safe and a tray icon belongs to the thread pumping its loop,
so everything GTK touches is built inside _run and every call from the daemon
thread arrives as an idle source. That mirrors tray.py, where the daemon thread
posts window messages rather than touching Win32 itself.

That loop must run the **global default** main context, and a private
thread-default context is not an option however tidy it looks. The menu is not
drawn locally, it is *exported* over com.canonical.dbusmenu, and while GDBus
will deliver the click on whatever context the object was built on,
libdbusmenu-gtk hands the last step — actually activating the GtkMenuItem — to
`g_idle_add`, which is hardcoded to the default context. Run anything else and
the D-Bus call still succeeds, the menu still looks right, and no menu item
ever fires. This was tried; it cost an afternoon.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from .config import Config
from .tray import (
    ICON_THEME_NAME,
    ID_LOGS,
    ID_QUIT,
    ID_SETTINGS,
    icon_png_path,
    menu_items,
    open_logs,
    open_settings,
    tooltip,
)

LOG = logging.getLogger(__name__)


def tray_host_available() -> tuple[bool, str]:
    """Can this session host a tray icon, and if not, is that worth reporting?

    Two different "no" answers, which deserve different log levels. A box with
    no graphical session at all — a server, a container, a CI runner — is doing
    nothing wrong and should stay quiet. A desktop session that is missing the
    typelib is a packaging problem someone can fix, and saying so is the only
    hint they will get, because the missing thing *is* the icon that would
    otherwise lead them to the log folder.
    """
    import os

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False, ""
    try:
        _import_gi()
    except (ImportError, ValueError) as exc:
        # ValueError is what gi.require_version raises for a missing typelib,
        # which is a different package from python3-gi itself.
        return False, (
            f"{exc}. Install python3-gi and gir1.2-ayatanaappindicator3-0.1 "
            f"for the tray icon."
        )
    return True, ""


def _import_gi():
    """Import the typelibs, or raise so the daemon can log and carry on.

    Kept in a function because require_version has to run before the first
    from-gi.repository import in the process, and because a missing typelib is a
    normal state on a headless box rather than a programming error.
    """
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3, GLib, Gtk

    return AyatanaAppIndicator3, GLib, Gtk


class LinuxTrayIcon:
    """The tray icon and the GLib loop it lives on."""

    def __init__(self, config: Config, on_quit: Callable[[], None], state_dir: Path):
        self.config = config
        self.on_quit = on_quit
        self.state_dir = state_dir
        self.connected = False
        self._indicator = None
        self._menu = None
        self._context = None
        self._glib = None
        self._gtk = None
        self._appind = None
        self._loop = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)

    # ------------------------------------------------------- daemon thread

    def start(self) -> None:
        """Start the loop and wait for it to prove it can build an icon.

        Waiting is what lets start() raise on a box with no typelib or no
        session bus, so the daemon logs one clear warning at startup rather than
        reporting a tray that silently never appears.
        """
        self._thread.start()
        self._ready.wait(timeout=10)
        if self._error is not None:
            raise self._error

    def update_config(self, config: Config) -> None:
        """Adopt an edited config: the menu reads admin_enabled from it."""
        self.config = config
        self._post(self._rebuild)

    def set_connected(self, connected: bool) -> None:
        """Called once per frame from the daemon; a no-op unless it changed."""
        if bool(connected) == self.connected:
            return
        self.connected = bool(connected)
        self._post(self._rebuild)

    def stop(self) -> None:
        self._post(self._quit_loop)
        self._thread.join(timeout=5)

    def _post(self, func) -> None:
        """Marshal onto the GLib thread; drop it if the loop is already gone.

        GLib.idle_add targets the global default context, which is exactly the
        one this thread runs, so it is both the simplest option and the correct
        one.
        """
        if self._glib is None:
            return
        self._glib.idle_add(func)

    # ---------------------------------------------------------- GLib thread

    def _run(self) -> None:
        try:
            self._appind, self._glib, self._gtk = _import_gi()
            # The global default context, deliberately — see the module
            # docstring. libdbusmenu-gtk activates the clicked GtkMenuItem from
            # a g_idle_add, which only ever runs on this context.
            self._context = self._glib.MainContext.default()
            # Both icons up front: writing one under the host's nose while it is
            # reading it is the same hazard tray.py avoids for the .ico.
            for state in (True, False):
                icon_png_path(state, self.state_dir)
            self._indicator = self._appind.Indicator.new(
                "usb-lcd-dashboard",
                f"{ICON_THEME_NAME}-idle",
                self._appind.IndicatorCategory.APPLICATION_STATUS,
            )
            self._indicator.set_icon_theme_path(str(self.state_dir))
            self._indicator.set_status(self._appind.IndicatorStatus.ACTIVE)
            self._rebuild()
            self._loop = self._glib.MainLoop.new(self._context, False)
        except BaseException as exc:  # noqa: BLE001 - handed to the daemon thread
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            self._loop.run()
        except BaseException:  # noqa: BLE001
            LOG.exception("Tray loop stopped")

    def _rebuild(self) -> None:
        """Rebuild icon and menu from (config, connected).

        Rebuilt wholesale rather than mutated because menu_items() is the single
        description of the menu on both platforms; reconciling it item by item
        would be a second, divergent copy of that logic.
        """
        if self._indicator is None:
            return
        name = f"{ICON_THEME_NAME}-{'live' if self.connected else 'idle'}"
        self._indicator.set_icon_full(name, tooltip(self.connected, self.config.device))
        # Ayatana renders no hover text of its own, so the status row that
        # tray.py greys out at the top of the menu is the only place it shows.
        self._indicator.set_title(tooltip(self.connected, self.config.device))

        menu = self._gtk.Menu()
        for item in menu_items(self.config, self.connected):
            entry = self._gtk.MenuItem(label=item.label)
            entry.set_sensitive(item.enabled)
            entry.connect("activate", self._on_activate, item.command)
            entry.show()
            menu.append(entry)
        menu.show_all()
        self._indicator.set_menu(menu)
        # No set_secondary_activate_target here, deliberately. It would bind
        # middle-click to the settings editor, but the menu is rebuilt whenever
        # the connection state changes, and set_menu destroys the old menu's
        # children — so the indicator is left holding a freed widget and trips
        # `gtk_widget_get_parent: assertion 'GTK_IS_WIDGET (widget)' failed` on
        # every reconnect. GNOME ignores the hint and opens the menu regardless,
        # so the gesture bought nothing on the platform being shipped to.
        #
        # Held on the instance, not just handed to set_menu: the indicator keeps
        # its own reference, but the menu owns the signal closures that make the
        # items do anything, and letting the Python side drop is how a menu ends
        # up visible but inert.
        self._menu = menu
        return False  # idle_add: run once

    def _on_activate(self, _widget, command: int) -> None:
        # INFO, not DEBUG: this one line separates "the click never arrived"
        # from "the click arrived and what it launched failed", which are
        # different bugs that look identical from the desk.
        LOG.info("Tray menu item %s activated", command)
        try:
            if command == ID_SETTINGS:
                open_settings(self.config)
            elif command == ID_LOGS:
                open_logs()
            elif command == ID_QUIT:
                LOG.info("Quit requested from the tray icon")
                self.on_quit()
                self._quit_loop()
        except Exception:
            # A menu item that fails must not take the icon — and with it the
            # only way to stop the daemon — down with it.
            LOG.exception("Tray menu action failed")

    def _quit_loop(self) -> None:
        if self._indicator is not None and self._appind is not None:
            self._indicator.set_status(self._appind.IndicatorStatus.PASSIVE)
        if self._loop is not None:
            self._loop.quit()
        return False
