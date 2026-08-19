# Notes — Linux parity

## The panel lives behind a KVM (confirmed by user 2026-08-19)
`1cbe:0092` disappears from the USB bus whenever the KVM hands the desk to the
other computer. Kernel log shows the whole `5-4.2.1` sub-hub dropping:

    usb 5-4.2.1:   USB disconnect, device number 64
    usb 5-4.2.1.3: USB disconnect, device number 66   <- panel

This is NOT a failing dock/hub — do not chase it as a hardware fault.

Consequence: `TuringUsbPanel` must survive disappear/reappear cycles. Today
`TuringUsbPanel.health_check()` is `return None`, i.e. a no-op, whereas
`SerialPanel.health_check` exists precisely because a silently reopened handle
paints crops at stale offsets (see commit 76e2cad, sleep/resume reconnect).
The USB panel needs the equivalent: notice the handle is dead, dispose it, and
re-run `find_device()` rather than writing into a stale one.

## tray.py DOES import on Linux
`from ctypes import wintypes` at tray.py:27 does not raise on Linux, so the
portable helpers (`menu_items`, `icon_image`, `tooltip`, `open_settings`,
`open_logs`) are reachable without restructuring the module. Only `start()`
needs to dispatch by platform.

## Ubuntu archive versions sit below the pyproject floors
pyproject asks `pyusb>=1.3` and `pycryptodome>=3.23`; Ubuntu ships
`python3-usb` 1.2.1 and `python3-pycryptodome` 3.20. Must confirm whether those
floors are real before writing the .deb Depends.

## /etc/udev/rules.d shadows /lib/udev/rules.d (bit this install)
udev does not merge same-named rules files across directories — it SKIPS the
`/usr/lib` one when `/etc` has the same filename. `/lib` is a symlink to
`/usr/lib` on Ubuntu, so installing to `/lib/udev/rules.d/` and to
`/etc/udev/rules.d/` collides on `99-turing-lcd.rules`.

This machine had a copy in `/etc` dated Jul 29, created by following
`README.md`'s run-from-source instructions, containing only the old tty rule.
It masked the updated packaged rule completely. Symptom was maddening: the
panel enumerated and `doctor` found it, but every frame failed — because the
raw `/dev/bus/usb` node is world-READABLE by default (so enumeration works)
and only writes need the rule.

    udevadm test /sys/bus/usb/devices/5-4.1 2>&1 | grep -i skipping
    -> Skipping overridden file '/usr/lib/udev/rules.d/99-turing-lcd.rules'.

That grep is the fastest way to spot it. Documented in README.md and
docs/packaging/linux.md.

## The venv cannot see PyGObject
`python3-gi` is a compiled extension tied to the system interpreter; pip's
pygobject needs build deps and is not a realistic install. A plain
`python3 -m venv` therefore gets `No module named 'gi'` and no tray icon, even
with the apt packages installed. Fixes, in order of cleanliness:

  1. `python3 -m venv --system-site-packages .venv`
  2. symlink `/usr/lib/python3/dist-packages/gi` into the venv site-packages
     (what this dev box does -- see the .venv, it is a symlink)
  3. run from the .deb, which uses the system python3 and has no such problem

Verified working here via (2). Documented in README.md.

## Verifying the tray actually registered
`gdbus ... ListNames | grep StatusNotifierItem` does NOT show it: Ayatana
registers under its unique bus name at `/org/ayatana/NotificationItem/<id>`,
not as a well-known `org.freedesktop.StatusNotifierItem-*` name. Ask the
watcher instead:

    gdbus call --session --dest org.kde.StatusNotifierWatcher \
      --object-path /StatusNotifierWatcher \
      --method org.freedesktop.DBus.Properties.Get \
      org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems

Look for `:1.NNNN@/org/ayatana/NotificationItem/usb_lcd_dashboard`, then map
the connection to a pid with `GetConnectionUnixProcessID` to be sure it is the
daemon and not some other tray app.

## The tray thread MUST run the global default GMainContext
Cost an afternoon; pinned by
`tests/test_tray.py::test_the_linux_tray_marshals_onto_the_default_main_context`.

A private `GLib.MainContext.new()` pushed as thread-default looks like the
textbook way to run GLib objects on a worker thread, and it is WRONG here.
appindicator does not draw the menu, it exports it over com.canonical.dbusmenu.
GDBus will happily deliver the incoming `Event` call on whatever context the
object was constructed on — but libdbusmenu-gtk performs the final step,
activating the GtkMenuItem, from a `g_idle_add`, which is hardcoded to the
default context. On a private context:

  - the icon appears, correctly
  - the menu renders, with correct labels and enabled states
  - `GetLayout` over D-Bus returns the right tree
  - the `Event` D-Bus call *succeeds*
  - and no menu item ever fires, with nothing logged anywhere

Diagnose it by firing the event yourself instead of relying on clicks:

    lay = bus.call_sync(dest, path, "com.canonical.dbusmenu", "GetLayout",
                        GLib.Variant("(iias)", (0, -1, ["label"])), ...)
    bus.call_sync(dest, path, "com.canonical.dbusmenu", "Event",
                  GLib.Variant("(isvu)", (item_id, "clicked",
                                          GLib.Variant("i", 0), 0)), ...)

`dest` is the unique bus name from StatusNotifierWatcher's
RegisteredStatusNotifierItems; the menu lives at <SNI path>/Menu.

## Menu items are inert unless the GtkMenu is held on the Python side
`indicator.set_menu(menu)` takes a C-side reference, but the menu owns the
signal closures. Letting the local go gives a menu that renders and does
nothing. Symptom is identical to the context bug above, which is what made the
two so confusing to tell apart.

## Menu actions that launch a program MUST use the desktop portal
The unit sets ProtectHome=read-only and PrivateTmp=true, and children inherit
it, so the daemon cannot start a desktop app itself. Measured inside a replica
of the unit's sandbox, on the same session bus, with marker URLs so the tab
that opened could be identified:

    plain xdg-open              exit 0, NOTHING OPENS
    systemd-run -- xdg-open     exit 0, NOTHING OPENS   (queued != ran)
    portal OpenURI              opens the tab           <- the only winner

Both losers report success. `systemd-run` without `--wait` reports only that
the *job was queued*; adding `--wait` gets a real exit code but it is still 0,
because xdg-open itself exits 0 having achieved nothing.

`tray.py:_open_via_portal` calls org.freedesktop.portal.OpenURI over the
session bus. open_logs needs it too, and the portal wants a URI, so the folder
goes through `Path.as_uri()`.

Verify with marker URLs and ask the human which tab appeared -- exit codes are
worthless here. Do not trust "it completed without raising".

## set_secondary_activate_target is not worth it
It binds middle-click, but set_menu destroys the old menu's children on every
rebuild, leaving the indicator holding a freed widget:
`gtk_widget_get_parent: assertion 'GTK_IS_WIDGET (widget)' failed` on every
reconnect. GNOME ignores the hint anyway. Removed.
