# How a frame happens

> **Covers:** `src/usb_lcd_dashboard/__init__.py`, `src/usb_lcd_dashboard/__main__.py`

Events flow one way. Nothing reads back up the chain.

```text
Claude Code / Codex
   │  a hook fires, one JSON object on stdin
   ▼
cli.py  emit / statusline-proxy          ── exits immediately, never draws
   │  {"schema_version": 1, "provider": …, "payload": …}
   ▼
transport.py                              ── Unix datagram, or TCP on Windows
   │
   ▼
daemon.py  run() loop, one event per tick
   │
   ├─► normalize.py ─► SessionState       ── + activity.py for the headline
   │        │
   │        ▼
   │   model.py  StateStore.apply()       ── merge into (provider, session_id)
   │        │
   │        ▼
   │   model.py  StateStore.assign(slots) ── who gets screen time
   │        │
   ▼        ▼
layout.py  compose(tiles, sessions)       ── per-tile, fault-isolated
   │        │
   │        └─► widgets/*  TileContext -> RGBA
   │        └─► background.py             ── the base layer
   ▼
display.py  paint()                       ── diff vs previous frame
   │  full frame, a crop, or nothing at all
   ▼
device.py  PanelDevice.write()            ── serial, or a PNG in simulation
```

## The two halves

**The hook half** is a short-lived process. It reads one JSON object, fires it
at a socket, and exits. It never renders, never blocks, and never fails because
the daemon is absent — see
[../runtime/transport.md](../runtime/transport.md#a-hook-must-never-crash-because-the-daemon-is-down).

**The daemon half** is a loop. It is the only thing that draws, the only thing
that holds the panel, and the only thing that needs a valid layout. That
asymmetry is the reason for strict versus lenient config loading
([invariants.md](invariants.md)).

## Where the interesting decisions live

| Question | Answered in |
| --- | --- |
| What does this event mean? | [normalize.py](../sessions/normalize.md) |
| Which sessions are on screen? | [model.py `assign()`](../sessions/model.md#assign--the-arbiter) |
| How many can be? | [`agent_slots`](../rendering/layout.md#slot-numbering) — derived from the layout |
| What does a tile look like? | [widgets](../rendering/widgets.md) |
| How much gets sent to the panel? | [display.py](../runtime/display.md) |
| How fast can it go? | [frame-budget.md](frame-budget.md) |

## Two panels

The 3.5" Turing panel (480×320) is the one that exists and works. The tile
system was built for a 1920×462 ultra-wide whose **transport is not settled** —
its manual carries no protocol, driver, resolution or USB id, and the bundled
driver supports none of its resolutions. `WindowPanel` raises on purpose.

Until that hardware is understood, `display.kind = "simulated"` renders the real
frame at the real size to `screencap.png`. The whole layout, every widget and
the tile arbitration are fully exercisable that way — see
[../runtime/device.md](../runtime/device.md#simulatedpanel).

## Entry points

`__main__.py` is three lines into `cli.main()`. `pyproject.toml` declares the
`usb-lcd-dashboard` console script pointing at the same place. Everything the
program does is a subcommand — see [../integration/cli.md](../integration/cli.md).

## See also

- [invariants.md](invariants.md) — the rules that hold across all of this.
- [frame-budget.md](frame-budget.md) — why things move as slowly as they do.
