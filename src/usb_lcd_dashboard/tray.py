"""A system tray icon, so the daemon is visible and can be stopped.

The daemon runs under console-less pythonw.exe with no window of any kind, which
means the only evidence it is alive is the panel itself — and when the panel is
unplugged or misconfigured there is no evidence at all. The tray icon is that
evidence, and its menu is the stop button.

Win32 directly through ctypes rather than pystray: the Windows installer ships a
frozen embedded CPython whose site-packages is assembled by build-installer.sh
from a fixed wheel list, so a new runtime dependency is a packaging change as
well as a code one. Shell_NotifyIcon is a handful of calls and no wheels.

The icon lives on its own thread with its own message loop, because a tray icon
is a window and a window belongs to the thread that pumps its messages. The
daemon thread never touches Win32 here; it posts messages (see set_connected)
and lets the tray thread act on them.
"""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .config import ADMIN_HOST, Config, config_home

LOG = logging.getLogger(__name__)

APP_NAME = "USB LCD Dashboard"

# Menu command ids. Any non-zero value works; these are just distinct.
ID_STATUS = 1
ID_SETTINGS = 2
ID_LOGS = 3
ID_QUIT = 4

# The icon glyph: a panel showing a lit screen. Green when the LCD is attached,
# grey when the daemon is running but has not found it.
FRAME_LIVE = "#2bc48a"
FRAME_DARK = "#6b7c8c"
SCREEN_LIVE = "#0d2b22"
SCREEN_DARK = "#151d24"
GLOW_LIVE = "#7defc0"
GLOW_DARK = "#3d4a56"

ICON_SIZES = (16, 20, 24, 32, 48, 64)

# The icon-theme basename the Linux tray resolves against its own state dir.
ICON_THEME_NAME = "usb-lcd-dashboard-tray"


@dataclass(frozen=True, slots=True)
class MenuItem:
    """One row of the tray menu, independent of Win32."""

    command: int
    label: str
    enabled: bool = True
    default: bool = False


def tooltip(connected: bool, device: str) -> str:
    """The hover text. Win32 truncates past 127 characters, so keep it short."""
    where = device if connected else "searching"
    text = f"{APP_NAME} - {'LCD connected' if connected else 'no LCD'} ({where})"
    return text[:127]


def menu_items(config: Config, connected: bool) -> list[MenuItem]:
    """The menu, as data.

    A disabled first row states what the icon's colour already hints at, since
    colour alone is a poor way to report a state someone may be squinting at in
    a 16-pixel square.
    """
    items = [
        MenuItem(
            ID_STATUS,
            "LCD connected" if connected else "Waiting for the LCD",
            enabled=False,
        )
    ]
    if config.admin_enabled:
        items.append(MenuItem(ID_SETTINGS, "Open settings...", default=True))
    items.append(MenuItem(ID_LOGS, "Open log folder"))
    items.append(MenuItem(ID_QUIT, f"Quit {APP_NAME}"))
    return items


def icon_image(connected: bool, size: int = 64) -> Image.Image:
    """Draw the tray glyph at one size.

    Rendered rather than shipped as a file so the two states cannot drift apart
    and the payload stays a pure code copy — build-installer.sh copies the
    package tree and nothing else.
    """
    frame = FRAME_LIVE if connected else FRAME_DARK
    screen = SCREEN_LIVE if connected else SCREEN_DARK
    glow = GLOW_LIVE if connected else GLOW_DARK

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    unit = size / 64
    # A 4:3 panel centred in the square, which is the shape of the real device.
    left, right = 4 * unit, 60 * unit
    top, bottom = 12 * unit, 52 * unit
    radius = max(1, round(5 * unit))
    border = max(1, round(4 * unit))
    draw.rounded_rectangle(
        (left, top, right, bottom), radius=radius, fill=screen, outline=frame,
        width=border,
    )
    # Two text lines on the screen, the dashboard's own shape in miniature.
    inset = border + 3 * unit
    line = max(1, round(5 * unit))
    draw.rectangle(
        (left + inset, top + inset, right - inset - 14 * unit, top + inset + line),
        fill=glow,
    )
    draw.rectangle(
        (
            left + inset,
            top + inset + line + 4 * unit,
            right - inset - 4 * unit,
            top + inset + 2 * line + 4 * unit,
        ),
        fill=frame,
    )
    return image


def icon_path(connected: bool, directory: Path) -> Path:
    """Write the multi-size .ico for one state, and return where it landed.

    LoadImage reads from a file, so the drawing has to become one. Written once
    per state per run and reused; a rewrite each time would put the file under
    the shell's nose while it is reading it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"tray-{'live' if connected else 'idle'}.ico"
    largest = icon_image(connected, max(ICON_SIZES))
    largest.save(target, format="ICO", sizes=[(n, n) for n in ICON_SIZES])
    return target


def icon_png_path(connected: bool, directory: Path) -> Path:
    """Write the PNG for one state, and return where it landed.

    The Linux counterpart of icon_path. StatusNotifierItem hosts take an icon
    *name* resolved against a theme directory rather than a file handle, so the
    name has to be stable and the file has to sit in a directory of its own —
    hence one PNG per state rather than the multi-size .ico Win32 wants.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{ICON_THEME_NAME}-{'live' if connected else 'idle'}.png"
    icon_image(connected, max(ICON_SIZES)).save(target, format="PNG")
    return target


def open_settings(config: Config) -> None:
    """Open the settings editor in a browser.

    `webbrowser.open` returning False is a silent failure — it means no handler
    could be started, and the menu item then does nothing with nothing logged,
    which is indistinguishable from a broken menu. Raise instead, so the caller
    logs it: this is the one menu item people actually use.

    On Linux it goes through the desktop portal, because the daemon's own
    sandbox stops it launching a browser directly. See _open_in_desktop.
    """
    url = f"http://{ADMIN_HOST}:{config.admin_port}/"
    if os.name != "nt":
        _open_in_desktop(url)
        return
    if not webbrowser.open(url):
        raise RuntimeError(f"no browser could be started for {url}")


def _open_via_portal(uri: str) -> None:
    """Ask the desktop portal to open a URI. Raises if it cannot.

    org.freedesktop.portal.OpenURI exists precisely for a process that cannot
    launch a desktop application itself, which is this daemon: it is a systemd
    user unit with ProtectHome=read-only and PrivateTmp=true, and everything it
    forks inherits that. The portal runs in the session instead, so nothing of
    ours constrains the browser it starts.

    This is measured, not assumed. Inside a replica of the unit's sandbox, with
    the same session bus:

        plain xdg-open           exit 0, nothing opens
        systemd-run -- xdg-open  exit 0, nothing opens
        portal OpenURI           opens the tab

    Both losers *report success*, which is what made this expensive to find.
    """
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.OpenURI",
        "OpenURI",
        # Empty parent window handle: we have no window to be transient for.
        GLib.Variant("(ssa{sv})", ("", uri, {})),
        None,
        Gio.DBusCallFlags.NONE,
        5000,
        None,
    )


def _open_directory_via_portal(folder: Path) -> None:
    """Ask the portal to show a local directory. Raises if it cannot.

    A separate call from _open_via_portal because OpenURI does not reliably
    handle `file://`: the portal cannot tell from a URI alone whether the asking
    process may see that path, so it wants a file descriptor it can check
    instead. Passing the folder as a URI is accepted and then quietly does
    nothing — the same silent-success failure as xdg-open.
    """
    import os as _os

    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    handle = _os.open(str(folder), _os.O_RDONLY)
    try:
        fd_list = Gio.UnixFDList.new()
        index = fd_list.append(handle)
        bus.call_with_unix_fd_list_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.OpenURI",
            "OpenDirectory",
            GLib.Variant("(sha{sv})", ("", index, {})),
            None,
            Gio.DBusCallFlags.NONE,
            5000,
            fd_list,
            None,
        )
    finally:
        _os.close(handle)


def _open_in_desktop(uri: str) -> None:
    """Open a URI in the user's session, however this machine can manage it.

    Portal first because it is the only route proven to work from inside the
    unit's sandbox; xdg-open and webbrowser after it, for a daemon run from a
    shell, a desktop with no portal, or a unit someone has loosened.
    """
    LOG.info("Opening %s", uri)
    try:
        _open_via_portal(uri)
        return
    except Exception as exc:  # noqa: BLE001 - any portal failure is a fallback
        LOG.warning("Desktop portal could not open %s: %s", uri, exc)

    opener = shutil.which("xdg-open")
    if opener:
        result = subprocess.run([opener, uri], capture_output=True, text=True)
        if result.returncode == 0:
            return
        LOG.warning(
            "xdg-open could not open %s (exit %s): %s",
            uri, result.returncode, result.stderr.strip(),
        )
    if not webbrowser.open(uri):
        raise RuntimeError(f"nothing could open {uri}")


def open_logs() -> None:
    """Show the folder holding dashboard.log, config.toml and the install state."""
    folder = config_home() / "usb-lcd-dashboard"
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(folder)  # noqa: S606 - a directory, opened in Explorer
    else:
        # Same sandbox problem as the settings editor, but a directory needs
        # OpenDirectory and a file descriptor rather than a file:// URI.
        LOG.info("Opening %s", folder)
        try:
            _open_directory_via_portal(folder)
            return
        except Exception as exc:  # noqa: BLE001 - fall back like the URI path
            LOG.warning("Desktop portal could not open %s: %s", folder, exc)
        _open_in_desktop(folder.as_uri())


# --------------------------------------------------------------------- Win32

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
# Our own three: the shell's icon callback, a connection-state change posted by
# the daemon thread, and a request to tear the icon down.
WM_TRAY = WM_APP + 1
WM_TRAY_STATE = WM_APP + 2

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXSMICON = 49
SM_CYSMICON = 50

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001
MF_DEFAULT = 0x1000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

CW_USEDEFAULT = -0x80000000
WS_OVERLAPPED = 0x00000000


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


if os.name == "nt":  # pragma: no cover - exercised only on Windows
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]


def _bind() -> tuple:  # pragma: no cover - Windows only
    """Declare the handful of Win32 calls used, with real argument types.

    ctypes defaults every argument to int, which silently truncates a 64-bit
    handle. Every call below therefore gets explicit types.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    ]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR
    ]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
    ]
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    return user32, shell32, kernel32


class TrayIcon:
    """The tray icon and its thread.

    Every Win32 object here is created and destroyed on the tray thread. The
    daemon only ever calls set_connected() and stop(), both of which post a
    message and return.
    """

    def __init__(self, config: Config, on_quit: Callable[[], None], state_dir: Path):
        self.config = config
        self.on_quit = on_quit
        self.state_dir = state_dir
        self.connected = False
        self.hwnd = None
        self._ready = threading.Event()
        self._thread = None
        self._icons: dict[bool, int] = {}
        self._taskbar_created = 0
        self._wndproc_ref = None
        self._data = None

    # -- the daemon's side ---------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="usb-lcd-tray", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            LOG.warning("Tray icon did not come up within five seconds")

    def update_config(self, config: Config) -> None:
        """Adopt an edited config: the tooltip and the menu both read from it."""
        self.config = config
        if self.hwnd is not None:
            self._user32.PostMessageW(self.hwnd, WM_TRAY_STATE, int(self.connected), 0)

    def set_connected(self, connected: bool) -> None:
        """Called once per frame from the daemon; a no-op unless it changed."""
        if connected == self.connected or self.hwnd is None:
            return
        self.connected = connected
        self._user32.PostMessageW(self.hwnd, WM_TRAY_STATE, int(connected), 0)

    def stop(self) -> None:
        if self.hwnd is not None:
            self._user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    # -- the tray thread's side ----------------------------------------------

    def _run(self) -> None:  # pragma: no cover - Windows message loop
        try:
            self._user32, self._shell32, kernel32 = _bind()
            self._wndproc_ref = WNDPROC(self._wndproc)
            instance = kernel32.GetModuleHandleW(None)
            klass = WNDCLASSEXW()
            klass.cbSize = ctypes.sizeof(WNDCLASSEXW)
            klass.lpfnWndProc = self._wndproc_ref
            klass.hInstance = instance
            # A pid suffix so two daemons (a test one on a spare port beside the
            # real one) do not collide on the class name.
            klass.lpszClassName = f"UsbLcdDashboardTray{os.getpid()}"
            if not self._user32.RegisterClassExW(ctypes.byref(klass)):
                raise ctypes.WinError(ctypes.get_last_error())
            # Never shown. It exists to own the icon and receive its callbacks;
            # a message-only window cannot, because the shell's TaskbarCreated
            # broadcast reaches top-level windows only.
            self.hwnd = self._user32.CreateWindowExW(
                0, klass.lpszClassName, APP_NAME, WS_OVERLAPPED,
                CW_USEDEFAULT, CW_USEDEFAULT, 0, 0, None, None, instance, None,
            )
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._taskbar_created = self._user32.RegisterWindowMessageW("TaskbarCreated")
            self._add_icon()
        except Exception as exc:
            LOG.warning("Tray icon unavailable: %s", exc)
            self._ready.set()
            return
        self._ready.set()

        message = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(message))
            self._user32.DispatchMessageW(ctypes.byref(message))

    def _icon_handle(self, connected: bool) -> int:  # pragma: no cover - Windows
        """Load (once) the HICON for a state."""
        if connected in self._icons:
            return self._icons[connected]
        path = icon_path(connected, self.state_dir)
        handle = self._user32.LoadImageW(
            None,
            str(path),
            IMAGE_ICON,
            self._user32.GetSystemMetrics(SM_CXSMICON),
            self._user32.GetSystemMetrics(SM_CYSMICON),
            LR_LOADFROMFILE,
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._icons[connected] = handle
        return handle

    def _notify_data(self) -> NOTIFYICONDATAW:  # pragma: no cover - Windows
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._icon_handle(self.connected)
        data.szTip = tooltip(self.connected, self.config.device)
        return data

    def _add_icon(self) -> None:  # pragma: no cover - Windows
        if not self._shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._notify_data())):
            raise ctypes.WinError(ctypes.get_last_error())

    def _update_icon(self) -> None:  # pragma: no cover - Windows
        self._shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._notify_data()))

    def _remove_icon(self) -> None:  # pragma: no cover - Windows
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        self._shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    def _show_menu(self) -> None:  # pragma: no cover - Windows
        menu = self._user32.CreatePopupMenu()
        for item in menu_items(self.config, self.connected):
            flags = MF_STRING
            if not item.enabled:
                flags |= MF_GRAYED
            if item.default:
                flags |= MF_DEFAULT
            self._user32.AppendMenuW(menu, flags, item.command, item.label)
        point = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(point))
        # Without this the menu refuses to dismiss on a click elsewhere; the
        # trailing PostMessage is the other half of the same long-standing
        # shell quirk, documented on TrackPopupMenu itself.
        self._user32.SetForegroundWindow(self.hwnd)
        chosen = self._user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            point.x,
            point.y,
            0,
            self.hwnd,
            None,
        )
        self._user32.PostMessageW(self.hwnd, 0, 0, 0)
        self._user32.DestroyMenu(menu)
        if chosen:
            self._invoke(chosen)

    def _invoke(self, command: int) -> None:  # pragma: no cover - Windows
        try:
            if command == ID_SETTINGS:
                open_settings(self.config)
            elif command == ID_LOGS:
                open_logs()
            elif command == ID_QUIT:
                LOG.info("Quit requested from the tray icon")
                self.on_quit()
                self._user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        except Exception:
            # A menu item that fails must not take the icon — and with it the
            # only way to stop the daemon — down with it.
            LOG.exception("Tray menu action failed")

    def _wndproc(self, hwnd, message, wparam, lparam):  # pragma: no cover - Windows
        if message == WM_TRAY:
            event = lparam & 0xFFFF
            if event == WM_RBUTTONUP:
                self._show_menu()
            elif event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK) and self.config.admin_enabled:
                self._invoke(ID_SETTINGS)
            return 0
        if message == WM_TRAY_STATE:
            self.connected = bool(wparam)
            self._update_icon()
            return 0
        if message == WM_COMMAND:
            self._invoke(wparam & 0xFFFF)
            return 0
        if message == self._taskbar_created and self._taskbar_created:
            # Explorer restarted and forgot every icon; put ours back.
            LOG.info("Explorer restarted; re-adding the tray icon")
            try:
                self._add_icon()
            except OSError as exc:
                LOG.warning("Could not re-add the tray icon: %s", exc)
            return 0
        if message == WM_CLOSE:
            self._remove_icon()
            self._user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            for handle in self._icons.values():
                self._user32.DestroyIcon(handle)
            self._icons.clear()
            self._user32.PostQuitMessage(0)
            return 0
        return self._user32.DefWindowProcW(hwnd, message, wparam, lparam)


def start(config: Config, on_quit: Callable[[], None], state_dir: Path | None = None):
    """Start the tray icon, or return None where there is no tray to start.

    Returns None where there is no tray to put an icon in — a headless box, or
    a desktop with no StatusNotifierItem host. The Linux install is a systemd
    user unit, so `systemctl --user stop` remains the stop button of last
    resort; the icon is an addition to that, not a replacement for it.
    """
    directory = state_dir or (config_home() / "usb-lcd-dashboard")
    if os.name != "nt":
        if not sys.platform.startswith("linux"):
            LOG.debug("No tray icon on %s", sys.platform)
            return None
        from .tray_linux import LinuxTrayIcon, tray_host_available

        available, reason = tray_host_available()
        if not available:
            # Not an error: a daemon with no icon is still a working daemon, and
            # `systemctl --user stop` is still the stop button.
            if reason:
                LOG.warning("Tray icon unavailable: %s", reason)
            else:
                LOG.debug("No graphical session; skipping the tray icon")
            return None
        icon = LinuxTrayIcon(config, on_quit, directory)
        icon.start()
        return icon
    icon = TrayIcon(config, on_quit, directory)
    icon.start()
    return icon
