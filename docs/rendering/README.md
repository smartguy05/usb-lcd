# Rendering

Everything that turns state into pixels.

| Document | Covers |
| --- | --- |
| [layout.md](layout.md) | `Tile`, `TileContext`, validation, `compose`, backgrounds. |
| [widgets.md](widgets.md) | The registry, the `base.py` helpers, and **how to add a widget**. |
| [crab.md](crab.md) | The animated widget, and the hardware constraints behind it. |
| [render.md](render.md) | Palette, fonts, text helpers, the legacy 480x320 card. |
| [screensaver.md](screensaver.md) | The deterministic moving clock used after inactivity. |

## Where to start

Adding a widget → [widgets.md](widgets.md#adding-a-widget). Three steps, and
nothing else needs to change — validation, slot counting and the settings form
all read the registry.

Anything that moves → [crab.md](crab.md) first, then
[../architecture/frame-budget.md](../architecture/frame-budget.md). Two hard
rules: nothing oscillates above ~0.63 Hz, and nothing animates at a tile's
outer edge.

Colours or fonts → [render.md](render.md#the-palette). Import the constants;
never write hex anywhere else.

## Two things that look like bugs and are not

- **The context bar is implemented twice.** `render.py` keeps its own copy
  because the legacy card is pinned pixel-for-pixel by a test. Do not
  deduplicate it.
- **Accent-by-phase logic exists three times**, each tuned to its own widget's
  palette needs.

Both are explained in [render.md](render.md#do-not-deduplicate-the-context-bar).

## See also

- [../sessions/README.md](../sessions/README.md) — where `TileContext.session` comes from.
- [../runtime/display.md](../runtime/display.md) — what happens to the composed frame.
