# The widget registry

> **Covers:** `src/usb_lcd_dashboard/widgets/__init__.py`, `src/usb_lcd_dashboard/widgets/base.py`, `src/usb_lcd_dashboard/widgets/agent.py`, `src/usb_lcd_dashboard/widgets/clock.py`, `src/usb_lcd_dashboard/widgets/legacy.py`, `src/usb_lcd_dashboard/widgets/messages.py`, `src/usb_lcd_dashboard/widgets/notifications.py`, `src/usb_lcd_dashboard/widgets/todos.py`

A widget is a plain function: `TileContext -> Image` of the tile's exact size,
in **RGBA** so a tile can be translucent over a wallpaper. That is the same
shape `render_dashboard` always had — they were full-screen widgets all along.

## The registry

`WIDGETS: dict[str, WidgetSpec]` (`widgets/__init__.py:60`).

| Name | `wants_session` | Notes |
| --- | --- | --- |
| `agent` | yes | The scalable session card. |
| `crab` | yes | The animated mascot. See [crab.md](crab.md). |
| `clock` | no | Time and date. |
| `legacy` | yes | The 480×320 original; meant to be the only tile. |
| `messages` | no | Latest human Discord message and local new-message count. |
| `notifications` | no | Filtered active Windows notifications, rotating newest-first. |
| `todos` | no | Prioritized pages from the persistent human action list. |

`WidgetSpec` (`:50`): `render`, `wants_session`, `wants_messages`,
`wants_notifications`, `wants_todos`, `options`,
`help`. The first flag assigns an agent session; the second is reserved for a
future provider-neutral messaging snapshot. Network work remains outside
rendering.

`Option(type, default, help)` (`:35`) with `type` in
`("bool", "text", "number", "color")`. `describe()` (`:105`) serialises the
registry for the settings editor, which is why a newly registered widget gets a
working form for free — see
[../admin/settings-editor.md](../admin/settings-editor.md).

`COMMON_OPTIONS` (`:42`): `background` (a colour, or `"transparent"`) and
`opacity`. Honoured by any widget built with `new_tile`.

## Adding a widget

1. Write `widgets/<name>.py` with `render_<name>(ctx) -> Image` returning RGBA
   of exactly `ctx.size`. Start from `new_tile(ctx.size, ctx.options)`.
2. Import it in `widgets/__init__.py` (`:24-27`).
3. Add a `WidgetSpec` to `WIDGETS`. Include `**COMMON_OPTIONS` unless the widget
   paints its own opaque background (as `legacy` does).

Nothing else changes. `validate` checks names against `WIDGETS`, `agent_slots`
and `compose` read `wants_session`, and `describe()` feeds the editor — all
automatically.

**`wants_session=True` is a behavioural choice, not a cosmetic one.** It makes
the tile consume a session slot, so a layout with one `agent` and one `crab`
shows *two different sessions*, not one session two ways.

Then: add tests to `tests/test_widgets.py` following the existing idioms, and
update `tests/test_widgets.py::test_the_registry_exposes_the_expected_widgets`
and `tests/test_admin.py::test_the_widgets_endpoint_describes_the_registry`,
which both assert the exact set.

## base.py — shared scaffolding

| Function | Line | Purpose |
| --- | --- | --- |
| `panel_fill(options)` | `base.py:14` | Resolve `background`+`opacity` to RGBA, or `None` for transparent. |
| `new_tile(size, options)` | `base.py:32` | Transparent canvas with the rounded card already drawn. |
| `context_bar(draw, box, percent, accent, *, label_size=0, gap=None)` | `base.py:46` | The "CONTEXT USED" meter. |

`context_bar` with `label_size=0` draws the track alone — what a tile too short
for a caption wants. It returns early if there is not even 3 px of room
(`:83-84`). The filled portion is floored at `left + radius * 2` so a near-zero
percentage still reads as a pill rather than nothing.

Its docstring records why `render.py` keeps a third, independent copy — see
[render.md](render.md#do-not-deduplicate-the-context-bar).

## agent.py

`render_agent(ctx)` (`agent.py:67`). The same information and reading order as
the legacy card, but every coordinate is a fraction of the tile, with the ratios
taken from the 480×320 original so that shape looks like the card it came from.

`_headline` (`:38`) prefers `state.activity` over the phase word for `TOOL`,
`THINKING` and `ACTIVE`, and forces `"APPROVAL NEEDED"` for `APPROVAL`.

`_empty` (`:51`) is deliberately quiet: *"several of these at once should not
compete with the ones that have something to say."* It shows the slot number and
either `NO ACTIVE SESSION` or `WAITING FOR LCD`.

## clock.py

`render_clock(ctx)` (`clock.py:16`). Options `title`, `hour12`, `seconds`,
`show_date`. Twelve-hour time drops the leading zero, matching `render_idle`.

With `seconds` on, it searches for a size that fits the clock **and** the
seconds together (`:36-49`) — sizing the clock alone pushes the seconds off the
edge.

## legacy.py

`render_legacy(ctx)` (`legacy.py:18`) is a nine-line adapter returning
`render_dashboard` or `render_idle`. It returns **RGB**, which is one of the
three conditions for the fast path in
[layout.md](layout.md#the-legacy-fast-path).

Its only option is `title`, overriding `dashboard.idle_title`. It omits
`COMMON_OPTIONS` because it paints its own opaque background.

## todos.py

`render_todos(ctx)` renders only the immutable snapshot supplied by the daemon.
Overdue, today, and seven-day deadlines lead; remaining items follow priority,
with manual position breaking equal tiers. Capacity derives from tile height and
pages change from `ctx.now` at `rotation_seconds`, so rendering is reproducible.

## Tests

`tests/test_widgets.py` — registry contents, and for each widget: exact size,
RGBA mode, every phase, every context percentage, containment within the tile,
and the `background`/`opacity` alpha probes. Parametrised over `SIZES`, which
includes two deliberately cramped strips nothing is tuned for.

## See also

- [crab.md](crab.md) — the animated widget, and the constraints it works under.
- [render.md](render.md) — palette, fonts, `_fit`.
- [layout.md](layout.md) — `TileContext`, `compose`, slots.
