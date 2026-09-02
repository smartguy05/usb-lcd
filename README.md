# USB LCD Dashboard

A status dashboard for Claude Code and Codex, driving either of two panels from
one config file per machine:

```text
480×320   3.5" Turing/UsbMonitor   USB 1a86:5722, serial USB35INCHIPSV2
1920×462  9.2" ultra-wide IPS      USB-C — transport not settled yet, see below
```

The 3.5" panel shows one session on one card. The ultra-wide is divided into
**tiles**, each holding a widget — a clock, an agent card, an animated crab,
selected-channel Discord messages, notifications, a human todo list, or Claude usage limits.

**To install it, jump to [Installing](#installing)** — there is a prebuilt
package for [Windows 11](#windows-11) and for [Ubuntu](#ubuntu).

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
widget = "clock"          # clock | agent | crab | messages | notifications | todos | claude_limits | legacy
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

**Only the daemon is that strict.** A tile rect is a display setting, and the
hooks never draw one — they need the IPC address and nothing else. So `emit`,
the status-line proxy, `install` and `uninstall` load a bad layout leniently,
warn, and carry on with the default one. Without that, a single typo'd widget
name makes every hook in every Claude and Codex session exit with a traceback,
and blocks the `install` that would repair the file. Everything outside the
layout is still checked for them, because a wrong `ipc.port` would silently send
the events nowhere. `doctor` is lenient too, and reports the bad layout as a
`FAIL` line naming the tile — it is the command you run precisely when something
is wrong.

A config with no `[[tile]]` table gets the 3.5" panel's full-screen layout, so an
existing install keeps working with no edits at all.

`[display.background]` sets a solid `color` and optionally an `image` with
`fit = "cover" | "contain" | "stretch" | "center"`. A background image that will
not load falls back to the colour and warns once, so a config shared between two
machines can name a wallpaper that only exists on one.

The settings editor can upload PNG, JPEG, or WebP wallpaper files into managed
storage. `card_opacity` controls the default translucency over an image; a
tile's explicit `opacity` still wins. The legacy full-screen dashboard also
reveals the wallpaper without changing its original no-wallpaper pixels.

`display.orientation` supports `landscape`, `portrait`,
`landscape_flipped`, and `portrait_flipped`. Choosing one in the editor rotates
the existing tile rectangles and canvas together, so no tile is left off-screen.

The moving-clock screen saver is enabled by default after ten minutes without
new agent events, messages, notifications, or todo changes:

```toml
[screensaver]
enabled = true
idle_seconds = 600
```

It uses a black background, moves once per minute, and wakes on the next piece
of dashboard activity.

See [config.example.wide.toml](config.example.wide.toml) for the full ultra-wide
layout.

## Messaging integrations

The `messages` widget shows the newest human message from selected Discord
server channels and a local count of messages received since **Clear new
messages** was pressed. It never marks anything read in Discord. Bots, webhooks,
DMs, forums and threads are excluded in this first version.

### Discord bot setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications),
   choose **New Application**, give it a name such as `USB LCD Dashboard`, and
   open the application.
2. Open **Bot** in the sidebar. Create the bot if Discord has not already done
   so, then enable **Message Content Intent** under **Privileged Gateway
   Intents**. Message metadata remains visible without it, but Discord removes
   the text and attachment fields that the LCD preview needs.
3. On the same page, choose **Reset Token** and copy the resulting bot token.
   Discord shows it only once. Treat it like a password; do not paste it into
   `config.toml`, a shell command, an issue, or a chat message.
4. Open **Installation** and enable a **Guild Install** using the `bot` scope.
   Grant only these bot permissions:

   - **View Channels**
   - **Read Message History**

   The dashboard never sends, edits, deletes, acknowledges, or reacts to
   messages, so it does not need **Send Messages**, **Manage Messages**, or
   administrator access.
5. Copy the generated install link, open it, select the server, and authorize
   the bot. Repeat this for every server containing channels you want on the
   LCD. You must have permission to add applications to each server.
6. Open the dashboard editor at <http://127.0.0.1:45723>. Add a `messages` tile
   from the layout picker if the layout does not already contain one, then click
   that tile. Discord settings live with the widget that shows them, so they
   appear on the **Widget settings** tab only while a `messages` tile is
   selected.
7. Under **Discord messages**, paste the bot token and choose **Save and
   verify**.
8. The editor discovers the server text channels visible to the bot. Check the
   channels to monitor, then choose the main **Save** button at the top of the
   page. Use **Refresh channels** after adding the bot to another server or
   changing channel permissions. The default tile title is `Discord`; that can be
   changed in the tile's options.

The count is local to the dashboard, not Discord's personal unread count. A
newly selected channel starts at its current newest message, so installing the
bot does not flood the LCD with history. **Clear new messages** resets the local
count without changing read state or messages in Discord.

The token is never returned by the local API or written to `config.toml`.
Windows encrypts it for the current user with DPAPI; Linux stores it in the
dashboard configuration directory with mode `0600`. **Disconnect** deletes the
stored token. If a token is ever exposed, reset it in the Developer Portal and
connect the dashboard again.

If no channels appear, confirm that the bot was installed in the server and
that both required permissions are allowed by the server role and any channel
overrides. If channel names appear but previews are empty, confirm that
**Message Content Intent** is enabled. DMs, group DMs, forum channels, threads,
bot posts, and webhook posts are intentionally excluded.

Do not paste a normal Discord user token. Discord forbids automating normal user
accounts (self-bots), and this integration rejects non-bot credentials.

## Human todos

The `todos` widget shows one global personal action list shared by the LCD,
settings editor, Claude Code, and Codex. Add a `todos` tile from the editor and
select it, then manage items under **Human todos** on the **Widget settings**
tab, or ask either agent to list, add, edit, complete, or reopen them. Completed
items leave the LCD but remain in history.

Items support details, priority, a date-only deadline, and manual ordering.
Overdue, today, and next-seven-day items lead; remaining items follow priority.
Large lists rotate in deterministic pages. The MCP tools explicitly describe
this as the human's list: agents may add concrete actions you need to take, but
must never use it for their own implementation plan or scratch work. Permanent
deletion requires an explicit request and confirmation.

## Claude limits

The `claude_limits` widget follows Claude's own usage display: a prominent
five-hour session meter, then weekly and Fable bars, each showing percentage
consumed and time until reset. Add it from the settings editor like any other
tile. Session and weekly values come directly from Claude Code's status-line
payload and the last known values survive dashboard restarts.

Claude Code does not currently expose its separate Fable allowance to status
lines, so that row uses a cached read-only request with Claude's existing OAuth
credential. The token is never logged or copied into dashboard state. If the
credential or endpoint is unavailable, only the Fable row disappears; hooks and
the other meters continue normally.

### Windows notifications

The Windows-only `notifications` widget reads the notifications currently held
by Windows, without an app-specific bot or API. In the settings editor, add a
`notifications` tile and select it — its access controls appear on the **Widget
settings** tab with the widget they belong to. Choose **Enable access**, approve
the Windows prompt, select the applications to show, and optionally enter
comma-separated include or exclude terms. Exclusion wins; otherwise any include
term may match the app name, title, or body.

Matching notifications rotate newest-first. The dashboard never dismisses them
and does not store their text on disk. Applications only appear in the picker
after emitting a notification, and an application that hides message previews
from Windows cannot be made to reveal them here.

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

## The active background (running fox)

The **active background** is a live wallpaper rather than a tile: a red fox that
runs across the whole panel *behind* every tile, disappears off one edge, waits a
beat, then re-enters from the other side. It is off by default. Turn it on from
the settings editor's **Active background** tab, or in `config.toml`:

```toml
[active_background]
enabled = true
scale = 0.45      # the fox's height as a fraction of the panel height
speed_min = 40    # pixels/second when the CPU is idle
speed_max = 220   # pixels/second when the CPU is pegged
opacity = 1.0     # fade the whole layer, 0..1
```

Its **speed follows CPU load**: the fox ambles when the machine is quiet and
sprints when it is busy, lerping between `speed_min` and `speed_max` from the
live CPU percentage (via `psutil`; if that is ever missing the fox simply runs at
a neutral speed rather than failing). This is the one thing here that cannot be a
normal widget — a tile is a pure function of the clock, but a position that is the
integral of a *varying* speed has to be carried between frames, so the layer is
stepped by the daemon and composited under the tiles.

Because it sits **behind** the tiles, an opaque tile card hides the fox where it
overlaps; you see it in the gutters and margins. Set a tile's card colour to
`transparent` to let more of it show through. The same wire limits as the crab
apply — the fox moves in ~2.4 fps steps, not a smooth glide, and a moving object
dirties the band it crosses — so it is deliberately a low-key backdrop.

The art is a six-frame run cycle under `assets/fox/`, baked by
`tools/make_fox_sprites.py`; drop your own equal-height RGBA `run_XX.png` frames
in to replace it.

## The settings editor

Rects are quick to render and awkward to type, so the daemon serves an editor at
**http://127.0.0.1:45723** where you drag them instead. Drag to move, drag the
corner handle to resize, snap to a grid, pick each tile's widget, and edit its
options — the form is generated from the widget registry, so a newly registered
widget appears there with working inputs and its own help text.

The canvas is always on screen because everything else is relative to a tile on
it. Below it sit a collapsed **Settings** panel for the things that belong to the
whole screen — background, screen saver, display — and three tabs: **Live
panel**, a view of the frame **actually on the panel**, which is why the editor
runs inside the daemon rather than as a separate tool; **Widget settings** for
whichever tile is selected (clicking a tile takes you there); and **Active
background**, where the running fox is turned on and tuned.

Settings for a *source* travel with the widget that shows it, so the Discord
connection appears only while a `messages` tile is selected, Windows notification
access only with a `notifications` tile, the human todo list only with a `todos`
tile, and the session timings only with a tile that takes a session.

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

## The tray icon

The daemon has no window on either platform — console-less `pythonw.exe` on
Windows, a systemd user unit on Linux — so without an icon there is nothing to
say it is alive and nothing to click to stop it. It puts one in the notification
area: **green when the LCD is attached, grey while it is still looking**, with
the resolved device in the hover text.

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

On Linux the icon is a StatusNotifierItem, drawn through
`gir1.2-ayatanaappindicator3-0.1`, which the `.deb` depends on. GNOME needs an
extension to show one at all — Ubuntu ships that enabled by default. Where no
tray host is running the daemon logs it and carries on, and
`systemctl --user stop usb-lcd-dashboard` remains the stop button.

One difference from Windows: the host owns the click gesture, so GNOME opens the
menu on left click rather than going straight to the settings editor. **Open
settings** is the first item either way.

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

## Multiple panels and the 9.2" ultra-wide panel

The 9.2" TURZX panel is supported directly over native USB (`1CBE:0092`) at
1920x462. A laptop that moves between it and the 480x320 serial panel can set
`display.kind = "auto"`: the daemon detects the attached hardware and restores
its saved layout from the `profiles/` directory beside `config.toml`. Configure
each panel once in the settings editor; later KVM and location changes switch
without editing canvas dimensions.

For development without hardware, use `kind = "simulated"`, which renders the real
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

## Installing

There is a prebuilt installer for each platform in `dist/`. Both do the same two
jobs — put the program on the machine, and wire it into your Claude and Codex
sessions — but they are packaged differently, because the platforms differ:

| | Windows 11 | Ubuntu 24.04+ |
| --- | --- | --- |
| Package | `USB-LCD-Dashboard-Setup-0.12.0.exe` | `usb-lcd-dashboard_0.12.0_all.deb` |
| Python | Bundled — nothing to install first | Uses the system `python3` and apt's Pillow/pySerial/numpy/pyusb/psutil |
| Size | 22.6 MB | 172.1 KB plus dependencies |
| SHA-256 | _pending a Windows build — see [WINDOWS.md](WINDOWS.md)_ | `4eca6f056f9b758e0ec52e21b6ab5c261f062e515e59d79864ed7bb7597f49d1` |
| Runs at login | Startup shortcut, with a tray icon | `systemd --user` service, with a tray icon |
| Hooks wired by | The installer, automatically | You, with one command |

> The 0.12.0 Windows installer is not yet in `dist/` — the identity-enabled
> `.exe` must be built on Windows (see [WINDOWS.md](WINDOWS.md)). The 0.12.0
> Ubuntu `.deb` above is built and smoke-tested.

Both are reversible, both preserve an existing Claude status line, and neither
displays prompts or transcript text.

Two things apply whichever you use. **A CLI that was already running will not
have the hooks** — start a new session. And **Codex asks you to trust newly
installed command hooks once**: run `/hooks` in Codex and trust the USB LCD
Dashboard definitions, or it will never emit anything.

### Windows 11

Double-click `dist\USB-LCD-Dashboard-Setup-0.12.0.exe`, or from a terminal:

```powershell
.\dist\USB-LCD-Dashboard-Setup-0.12.0.exe
```

It installs per-user into `%LOCALAPPDATA%\Programs\USB LCD Dashboard` — no
administrator rights needed — bundling its own Python runtime and dependencies.
It then auto-detects the panel as a COM port, installs the Claude Code and Codex
hooks for you, adds a startup shortcut, and launches the dashboard immediately.
There is nothing else to run.

The installer requests administrator approval so Windows can trust its
notification identity certificate. It is not code-signed, so SmartScreen may
also interrupt with a blue warning — **More info → Run anyway**. Add `/S` to
install silently instead (elevation is still required).

Check it afterwards from the Start menu's **Diagnostics** shortcut, or:

```powershell
& "$env:LOCALAPPDATA\Programs\USB LCD Dashboard\python.exe" -m usb_lcd_dashboard doctor
```

Uninstall from **Settings → Apps**, or the Start-menu Uninstall shortcut. That
removes the hooks and restores your status line; your config and its backups are
kept.

See [WINDOWS.md](WINDOWS.md) for the tray icon, the log file, and diagnostics.

### Ubuntu

Installing is two steps, because the package covers two different scopes. The
first is system-wide and needs root:

```bash
sudo apt install ./dist/usb-lcd-dashboard_0.12.0_all.deb
```

That lays down the program and the udev rule that creates `/dev/turing-lcd` and
grants you access to it. The second is per-user — the hooks and the service live
in your home directory — so run it **as yourself, not with `sudo`**:

```bash
usb-lcd-dashboard install
usb-lcd-dashboard doctor
```

That merges the Claude and Codex hooks, writes
`~/.config/usb-lcd-dashboard/config.toml`, and enables and starts the systemd
user service. It also installs the human-todo MCP tools into both clients; start
a new client session and use `/mcp` to verify them. If the panel was already plugged in, replug it so your session
picks up the new device permissions.

```bash
systemctl --user status usb-lcd-dashboard      # is it running
journalctl --user -u usb-lcd-dashboard -f      # what it is doing
```

To uninstall, do the per-user half first, while the package is still installed:

```bash
usb-lcd-dashboard uninstall
sudo apt remove usb-lcd-dashboard
```

See [LINUX.md](LINUX.md) for what goes where, keeping the panel alive without a
graphical login, and the diagnostics table.

### From source

Either platform, for development or for a machine you would rather not install a
package on. Use `.venv/Scripts/` instead of `.venv/bin/` on Windows:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/usb-lcd-dashboard install
```

`install` merges the hooks, preserves any existing Claude status line behind a
proxy, and on Linux writes and starts a systemd user unit. On Linux you also
need the udev rule, which the `.deb` would have shipped for you:

```bash
sudo install -m 0644 packaging/99-turing-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=1cbe
sudo udevadm trigger --subsystem-match=tty --attr-match=idVendor=1a86
```

The tray icon needs PyGObject, which is a compiled extension bound to the system
Python and not practically `pip`-installable. A virtualenv cannot see it unless
you ask for it:

```bash
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1
python3 -m venv --system-site-packages .venv     # note the flag
```

Without it the daemon starts fine and draws fine, and logs
`Tray icon unavailable: No module named 'gi'` — the panel is the job, and a
daemon with no icon is still a working daemon. On an existing venv, symlinking
`/usr/lib/python3/dist-packages/gi` into its `site-packages` works too. The
`.deb` runs on the system Python and has neither problem.

> **If you later install the `.deb`, remove this file.** The package ships the
> same filename under `/lib/udev/rules.d/`, and udev skips a `/usr/lib` rules
> file whenever `/etc` holds one of the same name — so a copy left here silently
> masks every future update to the packaged rule. `udevadm test /sys/... | head`
> says `Skipping overridden file` when that is happening. This bit a real
> install: a rule copied here predated TURZX support and kept the panel's raw
> USB node root-only long after the package knew better.

`usb-lcd-dashboard uninstall` reverses all of it. The system udev rule is
intentionally left for explicit removal.

### Upgrading

**Re-run `usb-lcd-dashboard install` after upgrading** — on Windows the
installer does it for you, on Ubuntu `apt install` of a newer `.deb` does not,
because the hooks are per-user. The set of hooks the dashboard registers grows
occasionally (`Notification`, which drives the crab's alarm, is new), and an
existing install keeps whatever it was set up with until `install` runs again. It
merges rather than replaces, so re-running is safe and leaves your own hooks and
status line alone.

### Building the installers

Both build in a container, so either can be built from either platform. Docker or
Podman required; the version comes from `pyproject.toml`.

```bash
packaging/windows/build-installer.sh    # -> dist/USB-LCD-Dashboard-Setup-<version>.exe
packaging/linux/build-deb.sh            # -> dist/usb-lcd-dashboard_<version>_all.deb
packaging/linux/smoke-test.sh           # installs the .deb in a throwaway container
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/usb-lcd-dashboard doctor
.venv/bin/usb-lcd-dashboard run --simulate
```

The simulator writes the current frame to `screencap.png`.

## Commands

- `run`: run the dashboard daemon, with the settings editor and (on Windows) the
  tray icon alongside it.
- `doctor`: inspect configuration, USB identity, permissions, hooks, and service.
- `doctor --paint-test`: display a test frame on the physical LCD.
- `emit --provider claude|codex`: consume one hook JSON object from stdin.
- `statusline-proxy`: preserve a Claude status line while forwarding its JSON.
- `install` / `uninstall`: manage reversible user-level integration.

This project is GPL-3.0-or-later because its display dependency is GPL-3.0.

