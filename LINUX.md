# Ubuntu package

`usb-lcd-dashboard_0.12.1_all.deb` installs the dashboard on Ubuntu 24.04 LTS
(noble) and later.

Unlike the Windows installer it does **not** bundle a Python runtime. Ubuntu
already ships everything needed — python3 3.12, Pillow, pySerial and numpy — so
the package depends on those and apt resolves them. The one exception is
`smartscreen-driver`, which is not in the archive; it is pure Python and GPLv3
like this project, so it is vendored into the package rather than becoming a pip
step that would need network access at install time.

The package is architecture-independent: nothing in it is compiled.

Built 2026-09-02 from the current source tree and smoke-tested on Ubuntu 24.04:

```text
dist/usb-lcd-dashboard_0.12.1_all.deb
sha256 14c3fdd006344f35338d43e0e42479ded6ff2a3e6e5e64334e7360b2aeefaebf
```

## Install

```bash
sudo apt install ./usb-lcd-dashboard_0.12.1_all.deb
```

That is the system-wide half: the program, and the udev rule that grants you
access to the panel — either `/dev/turing-lcd` for the 3.5" serial panel, or the
raw `/dev/bus/usb` node for a current-generation TURZX panel (`1cbe:*`), which
has no tty of its own.

The other half is per-user, because the hooks and the service live in your home
directory. Run it **as yourself, not with sudo**:

```bash
usb-lcd-dashboard install
usb-lcd-dashboard doctor
```

`install` merges the Claude and Codex hooks, preserves any existing Claude
status line behind a proxy, writes `~/.config/usb-lcd-dashboard/config.toml` if
you have none, installs the shared human-todo MCP tools, and enables and starts
the systemd user service.

If the panel was already plugged in when you installed the package, unplug and
replug it — or just log out and back in — so your session picks up the new
device permissions.

A CLI that was already running will not have the hooks, so start a new session.
Codex additionally asks you to trust newly installed command hooks once: run
`/hooks` in Codex and trust the USB LCD Dashboard definitions, or it will never
emit anything.

Open `http://127.0.0.1:45723` while the service is running to configure four-way
panel mounting, upload a managed PNG/JPEG/WebP wallpaper, and change the enabled
ten-minute moving-clock screen saver — all three live under the editor's
collapsible **Settings** panel. Portrait changes rotate the canvas and all tile
rectangles together.

## What went where

```text
/usr/bin/usb-lcd-dashboard                     the command
/usr/lib/python3/dist-packages/usb_lcd_dashboard/    the dashboard
/usr/lib/python3/dist-packages/smartscreen_driver/   the vendored panel driver
/lib/udev/rules.d/99-turing-lcd.rules          panel access (both transports)
/usr/share/doc/usb-lcd-dashboard/              this file, an example config
```

Per-user, created by `usb-lcd-dashboard install`:

```text
~/.config/usb-lcd-dashboard/config.toml        your layout
~/.config/usb-lcd-dashboard/profiles/           per-panel layouts in auto mode
~/.config/usb-lcd-dashboard/todos.sqlite3      human todo history
~/.config/usb-lcd-dashboard/install-state.json what to undo on uninstall
~/.config/systemd/user/usb-lcd-dashboard.service
~/.claude/settings.json, ~/.codex/hooks.json   merged, with a backup alongside
~/.claude.json, ~/.codex/config.toml           todo MCP server entries
```

## Running it

The service is a **user** unit, not a system one — it needs your session's
device access and your home directory:

```bash
systemctl --user status usb-lcd-dashboard
systemctl --user restart usb-lcd-dashboard
journalctl --user -u usb-lcd-dashboard -f
```

There is no log file on Linux — the daemon logs to the journal. There *is* a
tray icon, in the notification area, the same as on Windows: green when the
panel is attached, grey while it is still looking, and its menu opens the
settings editor. `systemctl --user` remains the stop button, and is the only one
where no tray host is running.

GNOME shows StatusNotifierItem icons only through an extension; Ubuntu enables
that by default. On a desktop that has none, or on a headless box, the daemon
logs that it found no tray and carries on.

To keep the panel alive when you are not logged in graphically:

```bash
sudo loginctl enable-linger "$USER"
```

## Diagnostics

```bash
usb-lcd-dashboard doctor
```

It checks the device, read/write access to it, the layout, both hook files, and
whether the service is running. It exits non-zero if anything fails, so it is
usable as a post-install self-test. On a fresh install with the panel unplugged
it will correctly report the device as missing.

| Symptom | Cause |
| --- | --- |
| `FAIL device` | Panel not plugged in, or the udev rule has not applied — replug it. The detail line names which panel is being waited for |
| `FAIL read/write access` | Rule applied but your session predates it; log out and back in. For a TURZX panel the detail line names the exact `/dev/bus/usb` node |
| No tray icon | Missing `gir1.2-ayatanaappindicator3-0.1`, or a desktop with no StatusNotifierItem host. `journalctl --user -u usb-lcd-dashboard \| grep -i tray` says which |
| Tray menu items do nothing | Missing `xdg-desktop-portal`. The daemon is a sandboxed unit and cannot launch a browser itself; the log says `Desktop portal could not open ...` |
| `FAIL service` | Not started: `systemctl --user enable --now usb-lcd-dashboard` |
| `FAIL layout` | `config.toml` names an unknown widget or an overlapping tile; the message names the offending one |
| Hooks fire but the panel never updates | The daemon is not running, or `[ipc]` in `config.toml` disagrees with the installed hooks |

## Uninstall

Remove the per-user half first, as yourself, while the package is still
installed:

```bash
usb-lcd-dashboard uninstall
```

That stops and disables the service, removes the unit, strips the hooks from
both files and restores the Claude status line it replaced. Your `config.toml`
and the backups it made are deliberately kept.

Then the system half:

```bash
sudo apt remove usb-lcd-dashboard
```

Package removal does not touch per-user state — it runs as root and cannot know
which users have it — so a hook left behind by skipping the first step would
keep pointing at a command that no longer exists. It fails harmlessly, but it is
untidy.

## Building the package

Needs Docker or Podman; it builds in an `ubuntu:24.04` container so it can be
built from any host, including Windows:

```bash
packaging/linux/build-deb.sh
```

The version comes from `pyproject.toml`, so that is the single place to change
it. Set `CONTAINER_RUNTIME=podman` to call podman directly, or `UBUNTU_IMAGE` to
target a different release.
