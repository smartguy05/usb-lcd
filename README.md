# USB LCD Dashboard

A status dashboard for Claude Code and Codex, driving either of two panels from
one config file per machine:

```text
480×320   3.5" Turing/UsbMonitor   USB 1a86:5722, serial USB35INCHIPSV2
1920×462  9.2" ultra-wide IPS      USB-C — transport not settled yet, see below
```

The 3.5" panel shows one session on one card. The ultra-wide is divided into
**tiles**, each holding a widget — a clock, an agent card, and more later.

The program does not display prompts, responses, or transcript text. It shows
only lifecycle metadata such as provider, model, project, elapsed time,
permission requests, and context used when the CLI exposes it.

The headline is the same activity line the agent prints above its own spinner —
"Editing src/render.py", "Running the installer build" — rebuilt from the tool
name and tool input the hook delivers. That is more useful than a bare tool
name, and it means the display can show file paths, search patterns, and command
descriptions taken from the current tool call.

## Tiles

A tile is an explicit pixel rect and the widget that owns it. Rects are given
rather than laid out: 1920×462 does not divide into whole squares, and a layout
is not portable between two panels this different anyway — so each machine keeps
its own `config.toml`.

```toml
[[tile]]
widget = "clock"          # clock | agent | legacy
x = 12
y = 12
w = 404
h = 438
[tile.options]
title = "HOME"
hour12 = true
seconds = true
show_date = true
background = "#101c28"    # or "transparent"
opacity = 0.75            # let a background image read through the card
```

Overlapping tiles, tiles that run off the panel, and unknown widget names are all
rejected when the config loads, naming the offending tile. Gaps are fine — the
background shows through them.

A config with no `[[tile]]` table gets the 3.5" panel's full-screen layout, so an
existing install keeps working with no edits at all.

`[display.background]` sets a solid `color` and optionally an `image` with
`fit = "cover" | "contain" | "stretch" | "center"`. A background image that will
not load falls back to the colour and warns once, so a config shared between two
machines can name a wallpaper that only exists on one.

See [config.example.wide.toml](config.example.wide.toml) for the full ultra-wide
layout.

## The settings editor

Rects are quick to render and awkward to type, so the daemon serves an editor at
**http://127.0.0.1:45723** where you drag them instead. Drag to move, drag the
corner handle to resize, snap to a grid, pick each tile's widget, and edit its
options — the form is generated from the widget registry, so a newly registered
widget appears there with working inputs and its own help text.

Alongside the canvas is a live view of the frame **actually on the panel**, which
is why the editor runs inside the daemon rather than as a separate tool.

Saving validates by round-tripping the candidate through the same loader the
daemon uses, so the editor cannot accept a config the daemon would then refuse to
start on, and a rejection reports the offending field or tile and writes nothing.
The file is replaced atomically; the daemon notices the new mtime and reloads
within a second, with no restart. A config that will not load is logged and
ignored, so a bad hand-edit never takes the panel down.

It binds loopback only, refuses any request whose `Host` header is not loopback,
and rewrites `config.toml` — so it is deliberately not bindable anywhere
routable. Turn it off with:

```toml
[admin]
enabled = false
port = 45723
```

Two caveats worth knowing. Saving **rewrites `config.toml` in canonical form**,
which drops any comments you added by hand. And `[ipc]` and `[admin]` are shown
but not editable there: changing the IPC transport would orphan the installed
hooks, and changing the editor's own port would cut off the page you are using.

## Several sessions at once

**The number of `agent` tiles is the cap on how many sessions show at once.**
With no more live sessions than tiles, every session gets its own tile and
nothing ever moves. Beyond that the surplus take turns.

A session takes a tile when it has an update that has not been shown yet and
keeps it for `switch_dwell_seconds`; a pending approval preempts immediately.
Without that floor a session emitting an event every second takes every frame,
and quieter sessions are never on screen long enough to read. An approval evicts
the tile that has been sitting longest rather than always the first one, so it
displaces the least recently interesting session instead of one that just
arrived.

A session that has nothing new does not take a turn, so a busy session is not
interrupted by an idle one. A session already on a tile is never moved to a
different tile, only evicted, so nothing hops around between frames. A session
waiting on a tool call emits nothing until the tool returns, which is why work in
flight expires on `tool_ttl_seconds` rather than the much shorter
`active_ttl_seconds`.

## The 9.2" ultra-wide panel

Its transport is **not settled**. The panel's manual contains no protocol,
driver, resolution or USB id — only safety boilerplate — and the bundled
`smartscreen-driver` supports 320×480, 480×800 and 600×1024, not 1920×462. So it
is either a display the OS enumerates as a monitor (`display.kind = "window"`) or
a different vendor serial protocol. Both sit behind the same `PanelDevice`
interface in `device.py`; `"window"` currently raises with a message saying so.

Until the hardware is in hand, use `kind = "simulated"`, which renders the real
frame at the real size to `screencap.png`. The whole layout, the widgets and the
tile arbitration are fully exercisable that way:

```bash
USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
  .venv/bin/usb-lcd-dashboard run --simulate
```

and then feed it events through the same path the hooks use:

```bash
echo '{"hook_event_name":"PreToolUse","session_id":"a","cwd":"'"$PWD"'",
       "tool_name":"Edit","tool_input":{"file_path":"src/layout.py"}}' \
  | USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
    .venv/bin/usb-lcd-dashboard emit --provider claude
```

## Windows 11

Use the self-contained `dist/USB-LCD-Dashboard-Setup-0.5.0.exe` installer. It
bundles its own Python runtime and dependencies, auto-detects the display as a
Windows COM port, installs Claude Code and Codex hooks, and starts at user login.
See [WINDOWS.md](WINDOWS.md) for installation and diagnostics.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/usb-lcd-dashboard doctor
.venv/bin/usb-lcd-dashboard run --simulate
```

The simulator writes the current frame to `screencap.png`.

## Installation

The installer merges user-level Claude and Codex hooks, preserves the existing
Claude status line, and installs a systemd user unit:

```bash
.venv/bin/usb-lcd-dashboard install
```

USB access requires the included device-specific udev rule:

```bash
sudo install -m 0644 packaging/99-turing-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty --attr-match=idVendor=1a86
```

Then enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now usb-lcd-dashboard.service
```

Use `usb-lcd-dashboard uninstall` to restore the backed-up CLI settings and
remove the user service/configuration created by the installer. The system udev
rule is intentionally left for explicit removal.

## Commands

- `run`: run the dashboard daemon, and the settings editor with it.
- `doctor`: inspect configuration, USB identity, permissions, hooks, and service.
- `doctor --paint-test`: display a test frame on the physical LCD.
- `emit --provider claude|codex`: consume one hook JSON object from stdin.
- `statusline-proxy`: preserve a Claude status line while forwarding its JSON.
- `install` / `uninstall`: manage reversible user-level integration.

This project is GPL-3.0-or-later because its display dependency is GPL-3.0.

