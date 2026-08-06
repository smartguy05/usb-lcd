# Windows 11 installer

`USB-LCD-Dashboard-Setup-0.2.0.exe` is a self-contained, offline installer for
64-bit Windows 11. It includes its own Python runtime, Pillow, pySerial, the
pinned SmartScreen driver, and the dashboard application. Python does not need
to be installed separately.

## Install

1. Copy the installer to the Windows 11 PC and double-click it.
2. Accept the install location and finish setup. The installer is not
   code-signed, so Windows SmartScreen may require **More info → Run anyway**.
3. Plug in the 3.5-inch display. Windows should expose this CDC device as a
   `USB Serial Device (COMx)` using its built-in `usbser.sys` driver.
4. Within a few seconds the LCD should replace its factory screen with the idle
   dashboard. The dashboard starts automatically at each user login.

The installer adds global Claude Code and Codex hooks without replacing other
configured hooks. If either CLI was already open, start a new session. Codex
requires newly installed command hooks to be reviewed once: run `/hooks` and
trust the USB LCD Dashboard definitions.

## Diagnostics

Open **Start → USB LCD Dashboard → Diagnostics**. It checks COM-port detection,
Claude hooks, Codex hooks, and login autostart. Runtime logs are stored at:

```text
%LOCALAPPDATA%\usb-lcd-dashboard\dashboard.log
```

The target display is detected first by serial `USB35INCHIPSV2`, then by USB
VID/PID `1A86:5722`. To force a particular port, edit:

```text
%LOCALAPPDATA%\usb-lcd-dashboard\config.toml
```

and change `device = "AUTO"` to a value such as `device = "COM4"`.

## Remove

Use **Settings → Apps → Installed apps → USB LCD Dashboard → Uninstall**. The
uninstaller stops the background process, removes its login shortcut and hooks,
and restores the previous Claude status-line configuration.

## Build the installer

From Linux with Docker installed:

```bash
packaging/windows/build-installer.sh
```

The result is written to `dist/USB-LCD-Dashboard-Setup-0.2.0.exe`.
