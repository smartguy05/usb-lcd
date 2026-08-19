# Completed — Linux parity

## Panel support (TURZX 1CBE:0092, 1920x462)
Root cause: the panel was already fully supported in code (`turing_usb.py`
declares `0x0092: (1920, 462)`, `device.py:TuringUsbPanel` drives it). What was
missing was every path *to* it on Linux.

- `packaging/linux/control` — added `python3-usb (>= 1.2.1)`,
  `python3-pycryptodome (>= 3.20)`. Deliberately below the pyproject floors
  (`pyusb>=1.3`, `pycryptodome>=3.23`); those came in with bulk bump c9257d8,
  not for any API, and Ubuntu ships only 1.2.1 / 3.20.
- `packaging/99-turing-lcd.rules` — added a `SUBSYSTEM=="usb"` rule for
  `1cbe:*`. These panels have no tty; libusb writes `/dev/bus/usb/*`, which is
  `crw-rw-r-- root root` by default: readable (so it is *found*) but not
  writable (so every frame fails). Matches on vendor only, on purpose.
- `device.py:_autodetect` — `display.kind="auto"` used to be a plain synonym for
  SerialPanel. Now maps size -> transport. Does NOT probe the bus (see notes.md
  re KVM).
- `device.py:TuringUsbPanel.health_check` — was `return None`. Now an 18-byte
  GET_DESCRIPTOR; `get_active_configuration` is pyusb-cached and useless here.
  `write()` translates `usb.core.USBError` -> `ConnectionError` so `Display`
  reconnects instead of dying.
- `doctor.py` — `_uses_usb_transport`, `usb_panel_node`, `detected_usb_device`.
  Reports `waiting for 1cbe:*` and names the `/dev/bus/usb` node for the access
  check. Previously said `waiting for 1a86:5722` at a USB panel.
  `TURZX_VID` is duplicated locally, not imported, so doctor still imports when
  pyusb is missing — pinned to `turing_usb.VENDOR_ID` by a test.

## Tray icon on Linux
- New `src/usb_lcd_dashboard/tray_linux.py` — StatusNotifierItem via
  AyatanaAppIndicator3/PyGObject. GTK built inside `_run`, all daemon-thread
  calls marshalled through `GLib.idle_add`.
- `tray.py` — added `icon_png_path` + `ICON_THEME_NAME` (SNI resolves an icon
  *name* against a theme dir, unlike Win32's multi-size `.ico`); `start()` now
  dispatches by platform.
- `tray_host_available()` distinguishes "headless, stay quiet" from "desktop
  missing the typelib, say which package to install".
- Portable half (`menu_items`, `icon_image`, `tooltip`, `open_*`) is shared, so
  the two platforms cannot drift in what the menu says.

## Docs / config
- `config.example.wide.toml` was stale (claimed kind="window", transport
  unknown) -> now `kind = "turing_usb"`.
- README.md, LINUX.md, docs/admin/tray.md, docs/runtime/device.md,
  docs/packaging/linux.md updated. `docs/runtime/device.md` had never been
  updated for TuringUsbPanel at all — it described WindowPanel at the line the
  USB panel now occupies.
- `build_index.py` + `search.py --check` both clean.

## Tests
538 pre-existing pass. Added: auto-detect (3), USB disconnect (3), doctor
transport/vendor (3), tray host availability + PNG icons (4).


## Verified on real hardware, 2026-08-19
Running from the packaged build (/usr/bin/usb-lcd-dashboard, system python3):

    OK  device             USB 1CBE:0092 (1920x462)
    OK  read/write access  /dev/bus/usb/005/074
    OK  layout             turing_usb 1920x462
    OK  service            active

Tray SNI registered at :1.NNNN@/org/ayatana/NotificationItem/usb_lcd_dashboard,
connection mapped back to the daemon's MainPID. Both menu items confirmed by
the user: settings editor opens a browser tab, log folder opens a Files window.
The user then rearranged tiles in that editor and the daemon reloaded live.

### Three wrong turns, for the record
1. A private thread-default GMainContext for the tray loop. Not a fix — a
   regression that broke every menu item. See notes.md.
2. "The sandbox blocks the browser" asserted without measuring, then
   `systemd-run --user` shipped as the fix. It opens nothing.
3. Trusting exit codes throughout. xdg-open, systemd-run and portal-OpenURI-
   with-a-file://-URI all report success while doing nothing.

What broke the loop: marker URLs (?probe=A/C/D) plus asking the human which
tab appeared, and firing com.canonical.dbusmenu Event directly instead of
relying on clicks. Both are written up in notes.md as the diagnostic recipe.
