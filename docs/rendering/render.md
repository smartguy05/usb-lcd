# render.py — palette, fonts, text helpers, legacy card

> **Covers:** `src/usb_lcd_dashboard/render.py`

Owns four things: the colour palette, cached font resolution, the text-fitting
helpers every widget uses, and the original 480×320 full-screen card that the
3.5" panel still draws.

## The palette

`render.py:20-29`. Import these rather than writing hex anywhere else.

| Constant | Value | Used for |
| --- | --- | --- |
| `BACKGROUND` | `#081018` | The frame behind everything. |
| `PANEL` | `#101c28` | A tile card's fill. |
| `TEXT` | `#f2f7fb` | Primary text. |
| `MUTED` | `#8aa0b2` | Labels and secondary text. |
| `CLAUDE` | `#d97757` | Claude accent (the orange the crab is drawn in). |
| `CODEX` | `#2bc48a` | Codex accent. |
| `WARNING` | `#ffca3a` | `APPROVAL`. |
| `ERROR` | `#ff5f69` | `ERROR`. |
| `TRACK` | `#1d3040` | The unfilled part of a meter. |

`LEGACY_WIDTH, LEGACY_HEIGHT = 480, 320` stay here rather than becoming a global
claim about "the display" (`:16-20`) — a second panel has its own size and gets
it from config.

## Fonts

`_font(size, bold=False)` (`render.py:33`), `lru_cache(128)`. The cache is
load-bearing, not tidiness (`:32-39`):

> render_dashboard alone calls this ~10 times per frame; four tiles make it ~40,
> each one otherwise parsing a TrueType file again.

Fallback chain, first success wins (`:40-56`):

1. `%WINDIR%/Fonts/segoeuib.ttf` / `segoeui.ttf`
2. `/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf`
3. DejaVu Sans (Bold/regular)
4. Liberation Sans
5. `ImageFont.load_default(size=size)` — Pillow's built-in

Step 5 is why the Ubuntu package depends on `fonts-dejavu-core`: a minimal
Ubuntu has **no TrueType font at all** and would silently fall to a bitmap face.
See [../packaging/linux.md](../packaging/linux.md).

## Text helpers

| Helper | Line | Behaviour |
| --- | --- | --- |
| `_fit(draw, text, width, size, bold=False, min_size=None)` | `:59` | Shrink to `min_size` if given, then ellipsize. Returns `(text, font)`. |
| `_wrap(draw, text, width, font)` | `:76` | Greedy wrap, force-splitting an over-long word. |
| `_fit_headline(draw, text, width, max_size=43)` | `:101` | One big line, else two smaller, else truncate the second. |
| `_duration(seconds)` | `:130` | `H:MM:SS` or `MM:SS`. |
| `_branch(cwd)` | `:140` | Git branch, cached 15 s. |

`_branch` shells out to `git branch --show-current` with a 150 ms timeout and
caches for `_BRANCH_TTL` (`:140-149`): *"three tiles at 2 Hz is six git
invocations a second."* Empty results are cached too, so a non-repo cwd stops
paying. It passes `NO_WINDOW` so the console does not flash on Windows.

## The legacy card

`render_dashboard(state, now)` (`:170`) and `render_idle(title, now, connected)`
(`:240`) return **RGB** images of exactly 480×320. Every coordinate is a literal.

They are reached through the `legacy` widget
([widgets.md](widgets.md#legacy)), which routes them through the tile composer
so there is one place slots are assigned and one place faults are handled.

### Do not deduplicate the context bar

`render_dashboard` draws its own context meter inline (`:211-222`), duplicating
`widgets/base.py:context_bar`. This is deliberate and permanent:

> Not widgets.base.context_bar: this card's output is pinned pixel for pixel by
> test_legacy_identical.py, and its caption sizing and fill floor differ from the
> tile version's. The duplication is deliberate.

The same applies, less formally, to accent-by-phase logic, which is implemented
independently three times (here, `widgets/agent.py:_accent`,
`widgets/crab.py:_colour_for`/`_accent_for`) because each is tuned to its own
widget.

## Tests

`tests/test_render.py`, `tests/test_legacy_identical.py`.

## See also

- [widgets.md](widgets.md) — every widget imports from here.
- [layout.md](layout.md) — the fast path that keeps the legacy card identical.
- [../architecture/invariants.md](../architecture/invariants.md)
