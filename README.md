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
widget = "clock"          # clock | agent | crab | legacy
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

## The crab

The `agent` tile tells you everything and catches your eye with nothing. The
`crab` tile is the other half of that trade: a crab in Claude orange that bobs,
blinks, scuttles and changes expression with what the agent is doing, over the
project name, the current activity line and the context-used bar.

It is drawn, not drawn *from* anything — no sprite ships with this, and there is
no asset directory. The crab is built out of Pillow primitives posed by a dozen
numbers, so it scales from a 300px tile down to a 60px one, and its expressions
are unit-testable without pinning a single pixel.

**When the agent wants you, the crab makes a scene**: both claws waving overhead,
wide unblinking eyes, an exclamation mark, and a border round the whole tile —
four cues at once, because any one of them alone is missable on a panel nobody is
looking at. That fires on `APPROVAL` (a permission prompt) and on `NOTICE` (the
`Notification` hook, which Claude Code fires when it needs permission or when you
have been sitting at a prompt). Approvals go warning yellow, notifications Claude
orange, so the two are distinguishable across the room.

The rest: `THINKING` looks up and away with a claw at its chin, `TOOL` scuttles
and snips, `COMPACTING` crouches and visibly packs, `ERROR` goes red and
crestfallen, `DONE` settles into a contented `^ ^`, and a finished or absent
session sleeps in grey with a `z`.

```toml
[[tile]]
widget = "crab"
x = 1424
y = 12
w = 484
h = 438
[tile.options]
color = ""             # blank follows the provider; orange for Claude, green for Codex
animate = true         # off draws one still pose
alarm = true           # off keeps the wave but drops the border
show_project = true
show_activity = true
show_context = true
```

A `crab` tile **takes a session slot exactly as an `agent` tile does**, so a
layout with one of each shows two different sessions, not one session two ways.

The tile drops text before it drops the crab as it gets smaller — caption, then
activity, then the whole text column (the crab moves beside the bar rather than
above it), then everything but the crab and a sliver of meter. Below about 44px
of crab there is no animal worth drawing, and the tile falls back to words.

### Frame rate

Animation needs frames. `refresh_hz` defaults to `2.0`; the crab wants about
`8.0`, which is what `config.example.wide.toml` now sets. That costs less than it
sounds: the panel is only sent the rectangle that actually changed, so a layout
of still widgets is no more expensive at 8Hz than at 2Hz, and a crab tile costs a
few percent of the frame budget.

**On the 3.5" panel the serial link is the real limit, not the loop.** It is a
115200-baud connection, and how fast a frame lands depends on how many pixels
changed. Measured on the hardware, a full-tile crab redrawing its own box
sustains about **2.4 frames a second**, and that is the ceiling however high
`refresh_hz` goes. Raising `refresh_hz` still helps a little — the loop's poll
timeout shrinks with it, which is worth about 0.4 fps between 2Hz and 8Hz — but
the crab on this panel is expressive rather than smooth, and that is a property
of the wire, not of the widget.

Two consequences the widget is designed around:

- **Nothing oscillates faster than 0.63Hz.** A wave needs roughly four samples
  per cycle to read as a wave rather than as claws teleporting, and at 2.4 fps
  that puts the ceiling near 0.6Hz. Faster is not merely wasted here, it looks
  worse.
- **The alarm border does not pulse.** Anything that animates at the tile's
  outer edge dirties the whole tile every frame instead of just the crab's box.
  Measured, a breathing border dropped the alarm from 2.2 fps to 0.8 fps — three
  times the bytes at the one moment responsiveness matters, to produce a pulse
  slower than the frame rate that read as random flicker. The border is a solid
  slab of colour; the claws, eyes and glyph carry the motion.

One more, still theoretical: the dirty-rect diff computes a **single** bounding
box, so two crabs at opposite ends of the ultra-wide union into a near-full-width
rect and fall back to full-frame writes.

If you would rather not raise the refresh rate, set `animate = false` and the
crab still changes expression with the phase — it just does not move.

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

## The tray icon (Windows)

On Windows the daemon runs under console-less `pythonw.exe`, so without an icon
there is nothing to say it is alive and nothing to click to stop it. It puts one
in the notification area: **green when the LCD is attached, grey while it is
still looking**, with the resolved port in the hover text.

- **Left click** opens the settings editor.
- **Right click** gives a menu: the current state, the settings editor, the log
  folder, and **Quit** — which is the same shutdown path as `SIGTERM` and the
  `shutdown` command, so the panel is released cleanly.

Windows 11 hides new icons behind the notification-area chevron; drag it onto
the taskbar to keep it visible. Turn the icon off with:

```toml
[tray]
enabled = true
```

There is no tray icon on Linux, where the install is a systemd user unit and
`systemctl --user stop usb-lcd-dashboard` is the stop button.

## Several sessions at once

**The number of session tiles (`agent` and `crab` alike) is the cap on how many
sessions show at once.**
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

**Re-run this after upgrading.** The set of hooks the dashboard registers grows
occasionally — `Notification`, which drives the crab's alarm, is new — and an
existing install keeps whatever hooks it was set up with until `install` runs
again. It merges rather than replaces, so re-running is safe and leaves your own
hooks and status line alone.

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

- `run`: run the dashboard daemon, with the settings editor and (on Windows) the
  tray icon alongside it.
- `doctor`: inspect configuration, USB identity, permissions, hooks, and service.
- `doctor --paint-test`: display a test frame on the physical LCD.
- `emit --provider claude|codex`: consume one hook JSON object from stdin.
- `statusline-proxy`: preserve a Claude status line while forwarding its JSON.
- `install` / `uninstall`: manage reversible user-level integration.

This project is GPL-3.0-or-later because its display dependency is GPL-3.0.

