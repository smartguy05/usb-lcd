# tray.py — the Windows notification-area icon

> **Covers:** `src/usb_lcd_dashboard/tray.py`

On Windows the daemon runs under console-less `pythonw.exe`, so without an icon
there is nothing to say it is alive and nothing to click to stop it. That is the
whole justification for this module.

There is no tray on Linux, where the install is a systemd user unit and
`systemctl --user stop usb-lcd-dashboard` is the stop button. `start()` returns
`None` on non-Windows by design.

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

`tooltip`, `menu_items`, `icon_image` and `icon_path` are deliberately pure
functions of their arguments, which is what makes them testable off Windows.

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

## Failure is never fatal

`_start_tray` in the daemon (`daemon.py:121-131`) catches everything and warns:
*"the panel is the job, and a daemon with no icon is still a working daemon."*
Turn it off with `[tray] enabled = false`.

## Tests

`tests/test_tray.py` — tooltip and menu contents for both states, the icon
differing between states, and the cached `.ico` path. The Win32 message loop
itself is marked `pragma: no cover` and exercised only on Windows.

## See also

- [settings-editor.md](settings-editor.md) — what left-click opens.
- [../runtime/daemon.md](../runtime/daemon.md) — the lifecycle calls.
- [../packaging/windows.md](../packaging/windows.md) — the embeddable runtime this constrains.
