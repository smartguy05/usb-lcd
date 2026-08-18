# layout.py — tiles and composition

> **Covers:** `src/usb_lcd_dashboard/layout.py`, `src/usb_lcd_dashboard/background.py`

Owns the tile model (`Tile`, `TileContext`), layout validation, slot numbering,
and `compose()` — which renders every tile, isolates a failing widget to its own
rectangle, and composites the frame over a background.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `Tile` | `layout.py:18` | An explicit pixel rect plus a widget name and options. |
| `TileContext` | `layout.py:48` | Everything a widget receives. |
| `validate(tiles, size)` | `layout.py:68` | Raises `ValueError`, naming the offending tile. |
| `agent_slots(tiles)` | `layout.py:98` | How many sessions can be on screen. |
| `compose(tiles, size, *, sessions, now, background, connected, idle_title)` | `layout.py:127` | The frame. |

### Tile

`widget`, `x`, `y`, `w`, `h`, `options`. Properties `.size`, `.origin`, `.rect`
(right/bottom exclusive, as Pillow wants).

Rects are explicit pixels rather than a column grid because 1920×462 does not
divide into whole squares and a layout is not portable between two panels this
different anyway — each machine keeps its own config.

### TileContext

| Field | Default | Meaning |
| --- | --- | --- |
| `size` | — | The exact pixel size the widget **must** return. |
| `now` | — | Frame timestamp. **All animation derives from this.** |
| `options` | — | This tile's options from config. |
| `session` | `None` | The assigned session, or `None`. |
| `slot` | `-1` | 0-based index for session-wanting tiles. |
| `connected` | `True` | Whether the panel is attached. |
| `idle_title` | `""` | Dashboard-level fallback title. |
| `messages` | `None` | Immutable integration snapshot for message-wanting widgets. |

It is **frozen**, and there is no per-widget state anywhere. Slow integration
work publishes immutable snapshots before composition; rendering never performs
network I/O. Animation remains a pure function of `now` — see
[crab.md](crab.md#animation-is-a-pure-function-of-ctxnow).

## Validation

`validate` (`layout.py:68`) rejects unknown widget names, non-positive sizes,
negative origins, off-panel rects, and overlaps — each error naming the tile
index and widget. It runs at **config-load time, not frame time**.

A shared edge is not an overlap (`_overlap`, `:58-65`): abutting tiles are a
normal layout. Gaps are fine too; the background shows through.

## Slot numbering

`agent_slots` counts tiles whose `WidgetSpec.wants_session` is true
(`layout.py:98-107`). The count is derived **from the layout** so it can never
disagree with it; `compose` then numbers slots by iteration order so nobody
hand-numbers them in config. Adding a session-wanting widget to a layout
therefore changes how many sessions the store places — a behavioural change, not
just a visual one.

## Fault isolation

`compose` wraps each `spec.render(context)` in a `try/except` and paints
`_fault_tile` (`:110-124`) instead — a red-outlined box naming the widget.
`layout.py:112-114`: *"The daemon used to drop the entire image on any render
fault, which with several tiles means losing three working ones to fix nothing."*

A widget returning the wrong size is cropped with a warning, not an error
(`:172-179`).

## The legacy fast path

If there is exactly one tile, at `(0, 0)`, sized to the full display, and its
rendered image is `mode == "RGB"`, `compose` returns that image object directly
— no background layer, no paste (`:144-148`, `:181-185`).

> Handing its image straight back — no base layer, no paste — is what makes that
> path byte-identical to calling render_dashboard directly.

This is what `tests/test_legacy_identical.py` depends on. All three conditions
matter; break any one and the legacy card silently routes through the normal
composite path instead. Still correct, no longer identical.

## background.py

`Background(color, image, fit, card_opacity)` and `background_layer(bg, size)`
(`background.py:23`, `:47`). Fit modes: `cover` (crop to fill), `contain`
(letterbox on `color`), `stretch` (ignore aspect), `center` (native size).

The cache is keyed by `(path, mtime, size, fit)` and holds exactly one entry —
`_CACHE.clear()` on every miss (`background.py:79`). Decoding and rescaling a
wallpaper every frame *"would cost more than everything else in the render path
put together"* (`:15-18`). Including mtime means replacing the file on disk is
picked up without a restart.

Every call returns `cached.copy()` (`:83-84`) because the caller composites onto
what it gets back. A missing or unreadable image warns **once per path** and
falls back to the solid colour; the warning flag is cleared if the file becomes
readable again.

When an image is configured, `card_opacity` supplies the default opacity for
tiles that do not set their own value. The legacy widget receives a special
wallpaper composite that makes its fills translucent while leaving text and
indicators opaque; with no image, the byte-identical fast path above is unchanged.

## Tests

`tests/test_layout.py` (validation, slot ordering, offsets, wrong-size crop,
fault isolation, the fast path), `tests/test_background.py`,
`tests/test_legacy_identical.py`.

## See also

- [widgets.md](widgets.md) — the registry and how to add one.
- [render.md](render.md) — the palette, fonts and text helpers.
- [../runtime/daemon.md](../runtime/daemon.md) — who calls `compose`.
- [../sessions/model.md](../sessions/model.md) — who fills `sessions`.
