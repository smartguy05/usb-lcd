# Invariants

Rules that hold across the whole repository. Each one exists because breaking it
caused a real problem. Read this before changing anything structural.

## Failures degrade, they never take the panel down

At every level there is a fallback rather than a crash:

| Failure | Result | Where |
| --- | --- | --- |
| A widget raises | That tile becomes a fault tile; the others still draw | [layout.py](../rendering/layout.md#fault-isolation) |
| `compose` raises | The frame is skipped; the last one stays up | [daemon.py](../runtime/daemon.md) |
| The config will not load | The last good one is kept | [daemon.py](../runtime/daemon.md#config-hot-reload) |
| The editor or tray will not start | Logged, and the daemon runs | [daemon.py](../runtime/daemon.md) |
| A wallpaper is missing | Warn once, fall back to the colour | [background](../rendering/layout.md#backgroundpy) |
| The daemon is not running | A hook exits 0 silently | [transport.py](../runtime/transport.md) |

## Strict for drawing, lenient for everything else

Only `run` loads the config strictly. Hooks, `install`, `uninstall` and `doctor`
tolerate a layout they will never draw, substituting the default and recording
why in `Config.layout_error`.

This is not tidiness. One unknown widget name in `config.toml` used to make
**every hook in every Claude and Codex session** exit with a traceback, and
blocked the `install` that would have repaired the file. Everything outside the
layout is still validated for those callers, because a wrong `ipc.port` would
silently send events nowhere — worse than a crash.

See [../runtime/config.md](../runtime/config.md#strict-vs-lenient-loading).

## The 3.5" panel is pixel-frozen

`tests/test_legacy_identical.py` renders the 480×320 card both ways in one
process and asserts identical pixels. Consequences:

- `compose` keeps a fast path that returns a single opaque full-screen tile's
  image **untouched** — same object, not a copy.
- `render.py` keeps its own duplicated context-bar drawing. **Do not
  deduplicate it.** Its caption sizing and fill floor differ from the tile
  version's on purpose.

See [../rendering/layout.md](../rendering/layout.md#the-legacy-fast-path).

## config.py is the single source of config truth

Defaults live in the `Config` dataclass. `default_config_toml` renders the
example and installed TOML *from* them, and a test asserts the examples have not
drifted. Adding a setting means touching `Config`, `parse_config` and
`dump_config_toml` — the last because tomllib reads but cannot write.

## The config file is the only channel between the editor and the daemon

No shared mutable state across threads. The editor writes atomically; the daemon
compares raw **bytes** once a second — not mtime, because a save can land inside
the same filesystem timestamp tick and would be silently ignored.

## The serial link, not the code, caps the frame rate

Measured: about 2.4 fps on the 3.5" panel. Therefore nothing in a widget should
oscillate above ~0.63 Hz, and **nothing should animate at a tile's outer edge**
— it dirties the whole tile and triples the bytes. See
[frame-budget.md](frame-budget.md).

## Widgets are pure functions of their context

`TileContext` is frozen and there is no per-widget state anywhere. Animation
must derive from `ctx.now`, never a counter or a wall-clock read. That is what
makes motion survive a session moving between tiles, and what makes any frame
reproducible in a test by naming its timestamp.

External integrations poll on their own worker and publish immutable snapshots
into `TileContext`; a renderer never waits for authentication or network I/O.

## Session slots come from the layout

`agent_slots` counts tiles whose widget declares `wants_session`. A standalone
number could only ever disagree with the tiles. Setting `wants_session=True` on
a new widget is therefore a behavioural change, not a visual one.

## LF endings in anything Linux executes

`.gitattributes` pins `*.sh`, `postinst`, `postrm`, the udev rule and the Debian
control files. A CRLF makes bash read `set -euo pipefail\r` as an invalid option
and would ship a `postinst` that cannot run. The Debian build strips CR again
anyway, because the failure would otherwise only surface on a user's machine at
install time.

## Live-daemon hazard

A real daemon may already hold IPC port 45722 (Windows) or the Unix socket. A
test daemon started without a spare port will bind-fail or feed the user's
physical panel. Use `USB_LCD_DASHBOARD_CONFIG` with distinct `ipc.port` and
`admin.port`.

**Never run `dist\*.exe` to inspect it** — NSIS `/S` performs a full install,
not an extraction.

## See also

- [overview.md](overview.md) — the flow these rules protect.
- [../testing/README.md](../testing/README.md) — the tests that enforce them.
