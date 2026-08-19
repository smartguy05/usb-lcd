# Windows 11 installer

`USB-LCD-Dashboard-Setup-0.11.0.exe` is a self-contained, offline installer for
64-bit Windows 11. It includes its own Python runtime, Pillow, pySerial, the
pinned SmartScreen driver, and the dashboard application. Python does not need
to be installed separately.

Built 2026-08-17 with tile support, the tray icon, the crab, direct USB,
filterable Windows notifications, shared human todos, and Claude limit meters:

```text
dist/USB-LCD-Dashboard-Setup-0.11.0.exe
sha256 32536024687d093146efc2209a6714c29418755b61f7c5d7314af95f7c3f9dde
```

Older installers in `dist/` predate the current notification-capable package.

## Install

1. Copy the installer to the Windows 11 PC and double-click it.
2. Approve the Windows administrator prompt, accept the install location, and
   finish setup. Elevation is needed to trust the notification identity's
   self-signed public certificate. The installer is not
   code-signed, so Windows SmartScreen may require **More info → Run anyway**.
3. Plug in the 3.5-inch display. Windows should expose this CDC device as a
   `USB Serial Device (COMx)` using its built-in `usbser.sys` driver.
4. Within a few seconds the LCD should replace its factory screen with the idle
   dashboard. The dashboard starts automatically at each user login.

The installer adds global Claude Code and Codex hooks without replacing other
configured hooks. If either CLI was already open, start a new session. Codex
requires newly installed command hooks to be reviewed once: run `/hooks` and
trust the USB LCD Dashboard definitions.

It also installs a user-scoped `usb-lcd-dashboard-todos` MCP server in both
clients. Restart an open client, then use `/mcp` to verify the human todo tools.

## The tray icon

The dashboard shows an icon in the notification area whenever it is running:
green with the LCD attached, grey while it is still looking for it, with the
resolved COM port in the hover text. Left-click opens the settings editor;
right-click offers the editor, the log folder, and **Quit**, which stops the
background process the same way the uninstaller does.

Windows 11 puts a newly registered icon behind the chevron (`^`) at the left of
the notification area. Drag it out onto the taskbar to keep it in view.

To run without one, set `enabled = false` under `[tray]` in `config.toml`. Note
that with no icon and no console window there is then nothing to stop the
dashboard with except `python.exe -m usb_lcd_dashboard shutdown`.

## Diagnostics

Open **Start → USB LCD Dashboard → Diagnostics**. It checks COM-port detection,
Claude hooks, Codex hooks, login autostart, and Windows notification identity,
bindings, and access. Runtime logs are stored at:

```text
%LOCALAPPDATA%\usb-lcd-dashboard\dashboard.log
```

The target display is detected first by serial `USB35INCHIPSV2`, then by USB
VID/PID `1A86:5722`. To force a particular port, edit:

```text
%LOCALAPPDATA%\usb-lcd-dashboard\config.toml
```

and change `device = "AUTO"` to a value such as `device = "COM4"`.

The tray's settings editor also provides four mounting orientations, a managed
PNG/JPEG/WebP wallpaper upload with translucent cards, and the screen-saver
enable/delay controls. Portrait selections rotate the canvas and every tile;
the default screen saver shows a moving clock after ten minutes and wakes on
new dashboard activity.

### After unplugging the display

Re-plugging the panel resets it: the framebuffer clears and the orientation
returns to the hardware default. The driver hides this, because it recovers from
the resulting write error by quietly reopening the COM port and retrying, without
replaying the panel's initialisation. Before 0.3.1 that left a sideways, fuzzy or
white screen, because the dashboard kept sending diff-sized crops to a panel that
no longer matched its idea of what was on screen.

The dashboard now notices that the port was reopened, reconnects, and repaints a
full frame, so a re-plug recovers on its own within a few seconds. `dashboard.log`
records it as:

```text
LCD write failed: serial port was reopened by the driver
LCD connected at COM10
LCD full frame written: 480x320
```

### After Windows sleep

Windows sleep invalidates the open LCD connection on some USB controllers. When
the dashboard notices the long runtime pause on resume, it discards that handle,
reopens the display, and repaints a full frame. You can also launch **USB LCD
Dashboard** again from the Start menu: when the background process is already
running, the shortcut requests the same reconnect instead of silently exiting
because the dashboard port is in use.

## Remove

Use **Settings → Apps → Installed apps → USB LCD Dashboard → Uninstall**. The
uninstaller stops the background process, removes its login shortcut and hooks,
and restores the previous Claude status-line configuration.

## Build the installer

From Linux, or from Windows under Git Bash, with Docker or Podman running:

```bash
packaging/windows/build-installer.sh
```

Podman serves the Docker API, so it needs no configuration beyond a started
machine. Set `CONTAINER_RUNTIME=podman` to call it directly instead.

The result is written to `dist/USB-LCD-Dashboard-Setup-0.11.0.exe`.
