# tray.py / tray_linux.py — the notification-area icon

> **Covers:** `src/usb_lcd_dashboard/tray.py`, `src/usb_lcd_dashboard/tray_linux.py`

The daemon has no window on either platform — console-less `pythonw.exe` on
Windows, a systemd user unit on Linux — so without an icon there is nothing to
say it is alive and nothing to click to stop it. That is the whole justification
for these modules.

`tray.py` holds the portable half and the Win32 backend; `tray_linux.py` holds
the StatusNotifierItem backend. `start()` dispatches on the platform and returns
`None` where there is no tray host to talk to — a headless box, or a desktop
without one. `systemctl --user stop usb-lcd-dashboard` remains the stop button
of last resort on Linux.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `tooltip(connected, device)` | `tray.py:69` | Hover text, naming the resolved port. |
| `menu_items(config, connected)` | `tray.py:76` | The right-click menu, as data. |
| `icon_image(connected, size=64)` | `tray.py:97` | The icon, drawn with Pillow. |
| `icon_path(connected, directory)` | `tray.py:139` | Cached `.ico` on disk. |
| `open_settings(config)` / `open_logs()` | `:153` / `:157` | Menu actions. |
| `TrayIcon(config, on_quit, state_dir)` | `tray.py:321` | The icon itself. |
| `.start()` / `.stop()` / `.set_connected(bool)` / `.update_config(cfg)` | `:336`-`:355` | Lifecycle, called from the daemon loop. |

| `icon_png_path(connected, directory)` | `tray.py:152` | Cached `.png`, for SNI. |
| `LinuxTrayIcon(config, on_quit, state_dir)` | `tray_linux.py:88` | The Linux icon. |
| `tray_host_available()` | `tray_linux.py:44` | Can this session host one, and is the "no" worth logging. |

`tooltip`, `menu_items`, `icon_image` and `icon_path` are deliberately pure
functions of their arguments, which is what makes them testable off Windows —
and what keeps the two backends from drifting apart in what the menu says. Both
build their menu from the same `menu_items()`.

The two backends want different image formats: Win32's `LoadImage` takes a
multi-size `.ico` file, while an SNI host resolves an icon *name* against a
theme directory, so Linux writes one `.png` per state named for it.

## States

Green when the LCD is attached, grey while it is still looking:

| Constant | Live | Idle |
| --- | --- | --- |
| `FRAME_*` | `#2bc48a` | `#6b7c8c` |
| `SCREEN_*` | `#0d2b22` | `#151d24` |
| `GLOW_*` | `#7defc0` | `#3d4a56` |

## Behaviour

- **Left click** opens the settings editor.
- **Right click** gives the current state, the settings editor, the log folder,
  and **Quit** — which calls the daemon's `stop`, the same shutdown path as
  `SIGTERM` and the `shutdown` command, so the panel is released cleanly.

Windows 11 hides newly registered icons behind the chevron; drag it onto the
taskbar to keep it visible.

## Why Win32 rather than pystray

`tray.py:8-11` records it: a packaging constraint. The Windows installer bundles
an embeddable CPython, and adding a tray library would mean adding it and its
dependencies to that payload. The icon is drawn with Pillow (already a
dependency) and registered through `ctypes` against the Win32 API.

## Why AppIndicator rather than raw D-Bus on Linux

The mirror image of the Win32 argument: the `.deb` depends only on Ubuntu
archive packages, and `python3-gi` plus `gir1.2-ayatanaappindicator3-0.1` are
both in the archive. Speaking StatusNotifierItem directly would mean
implementing `com.canonical.dbusmenu` in this repo to get a menu at all.

GTK is not thread-safe and a tray icon belongs to the thread pumping its loop,
so `tray_linux.py` builds everything inside `_run` and marshals every call from
the daemon thread through `GLib.idle_add` — the same shape as the Win32 backend,
which posts window messages rather than touching Win32 off its own thread.

One behavioural difference worth knowing: the host owns the click gesture, so
GNOME opens the menu on left click instead of activating the default item.
`set_secondary_activate_target` is a request, not a guarantee.

## Opening things from inside the sandbox

The Linux daemon is a systemd user unit with `ProtectHome=read-only` and
`PrivateTmp=true`, and every process it forks inherits that. It therefore
cannot start a browser or a file manager itself, and must ask the desktop
portal to do it.

Measured inside a replica of the unit's sandbox, on the same session bus, with
marker URLs so the tab that appeared could be identified:

| Route | Exit code | Opens anything? |
| --- | --- | --- |
| plain `xdg-open` | 0 | **no** |
| `systemd-run --user -- xdg-open` | 0 | **no** |
| portal `OpenURI` | success | **yes** |

Both losers report success, which is what makes this expensive to diagnose:
there is no error anywhere, the menu item simply does nothing. `systemd-run`
without `--wait` reports only that the *job was queued*; adding `--wait` still
yields 0, because `xdg-open` itself exits 0 having achieved nothing.

Two portal calls, not one:

- `_open_via_portal` → `OpenURI`, for the settings editor's `http://` URL.
- `_open_directory_via_portal` → `OpenDirectory`, for the log folder. A
  directory needs a **file descriptor**, not a `file://` URI — the portal
  cannot tell from a URI alone whether the caller may see that path, so it
  accepts the URI and quietly does nothing.

`xdg-open` and `webbrowser` remain as fallbacks for a daemon run from a shell
or a desktop with no portal. `tests/test_tray.py` pins the ordering, because
reordering it breaks the menu silently on a normal install.

## Failure is never fatal

`_start_tray` in the daemon (`daemon.py:121-131`) catches everything and warns:
*"the panel is the job, and a daemon with no icon is still a working daemon."*
Turn it off with `[tray] enabled = false`.

## Tests

`tests/test_tray.py` — tooltip and menu contents for both states, the icon
differing between states, the cached `.ico` and `.png` paths, and the two ways a
Linux session can lack a tray (no graphical session — quiet; no typelib —
reported with the package names to install). Neither message loop is exercised:
both need a real shell to talk to.

## See also

- [settings-editor.md](settings-editor.md) — what left-click opens.
- [../runtime/daemon.md](../runtime/daemon.md) — the lifecycle calls.
- [../packaging/windows.md](../packaging/windows.md) — the embeddable runtime this constrains.
