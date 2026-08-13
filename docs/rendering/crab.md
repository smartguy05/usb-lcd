# crab.py — the animated widget

> **Covers:** `src/usb_lcd_dashboard/widgets/crab.py`

A session shown as a crab that bobs, blinks, scuttles and changes expression
with the phase, and waves both claws when the agent needs you. No sprite ships
with this project and there is no asset directory — the crab is built from
Pillow primitives posed by about twenty numbers.

Read this before changing anything that moves. Most of its design is forced by
measurements, not taste.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `CrabPose` | `crab.py:65` | Every animatable value, as plain numbers. |
| `crab_pose(phase, t, *, alarm=True) -> CrabPose` | `crab.py:181` | Pure: phase + time in, pose out. |
| `draw_crab(draw, box, pose, colour, *, detail="full")` | `crab.py:548` | Draw into a box, back to front. |
| `render_crab(ctx) -> Image` | `crab.py:705` | The widget: layout, text, crab, border. |

Constants: `ASPECT = 1.35`, `MIN_CRAB_HEIGHT = 44`,
`ALARM_PHASES = {"APPROVAL", "NOTICE"}`, `SLEEPING_PHASES = {"ENDED"}`,
`BLINK_BUCKET = 3.0`, `BLINK_DURATION = 0.16`.

`CrabPose` fields include `bob`, `lean`, `squash`, `eye_open`, `happy_eyes`,
`pupil_dx/dy`, `claw_l/r`, `gape_l/r`, `brow`, `mouth`, `mouth_open`,
`leg_phase`, `leg_amp`, `glyph`, `glyph_pulse`, `border`, `sweep` — all
documented inline at `crab.py:65-92`.

## Animation is a pure function of `ctx.now`

`TileContext` is frozen and a widget is a plain function, so there is nowhere to
keep state. From the module docstring (`crab.py:9-15`):

> That is not a workaround: it means the animation has no epoch to drift, a
> session moved between tiles never restarts mid-stride, and any frame is
> reproducible in a test by naming its timestamp.

`t` must be `ctx.now.timestamp()` — absolute POSIX seconds. **Never** build it
from `now.second`, which wraps at 60 and would snap the crab once a minute
(`:184-187`).

### Phase changes must not rewind it

`_oscillators(t)` (`:151`) has **fixed frequencies and a fixed epoch**. A phase
change swaps only the coefficients applied to them, so a crab halfway through a
breath stays halfway through it across `READY -> TOOL -> DONE`. Where a
discontinuity is wanted — anything to `APPROVAL` — it reads as a snap to
attention.

`tests/test_crab.py::test_a_phase_change_does_not_rewind_the_crab` is the guard.
If someone gives a phase its own epoch, that test fails.

## Two constraints from the hardware

Both are measured, both are recorded in comments, and both look like arbitrary
choices until you know why.

### Nothing oscillates above 0.63 Hz

`crab.py:158-166`:

> The 3.5" Turing screen is a 115200-baud serial link, and the frame rate it
> sustains is set by how many pixels changed: measured, a crab that redraws its
> own box manages about 2.2 fps. A wave needs roughly four samples per cycle to
> read as a wave rather than as the claws teleporting, so anything faster than
> ~0.55 Hz is not merely wasted on this hardware, it actively looks worse.

### Why the alarm border does not pulse

`crab.py:216-225`:

> The panel is only sent the rectangle that changed between frames, and a border
> that breathes is a change at the tile's outer edge — so it dirties the whole
> tile every frame and triples the bytes over the serial link at the one moment
> responsiveness matters. Measured on the 3.5" panel: a pulsing border drops
> 2.2fps to 0.8fps.

The general rule for any future widget: **do not animate at a tile's outer
edge.** See [../runtime/display.md](../runtime/display.md) and
[../architecture/frame-budget.md](../architecture/frame-budget.md).

## Drawing notes that will bite you

- **`ImageDraw` replaces, it does not blend.** A translucent fill punches a hole
  through what is under it rather than tinting it. The shell highlight is drawn
  fully opaque for exactly this reason (`:614-617`), and the happy-eye caret
  needs an opaque ball behind it (`:493-496`).
- **`ImageDraw` does not antialias**, and this is all curves and thin diagonal
  limbs, so `_supersample` (`:620`) draws oversized and scales down.
- **Use `Image.reduce()`, not `resize()`** (`:625-628`): an exact integer box
  filter, no ringing around the dark pupil, about twice as fast. Factor is 4/3/2
  by target height.
- **Prefill the canvas with the crab's own RGB at zero alpha** (`:627-631`), not
  transparent black — averaging happens on straight alpha, so transparent black
  neighbours drag edge pixels dark and leave a halo.
- The blink schedule uses a written-out **splitmix64** (`_mix`, `:103`), not
  `hash()`, which is salted per process and would make the schedule untestable.
- Claws stay below 90° in the alarm (`:205-210`) — past vertical the forearm
  folds inward and the claw pokes the eyestalk, muddling the silhouette exactly
  when it matters most.
- `draw_crab` never knows whether it is being supersampled (`:559-561`), which
  keeps it directly unit-testable and lets the still path skip the cost.

## Size ladder

`render_crab` picks a layout from the tile (`:736-810`), dropping text before it
drops the crab:

| Tile | Layout |
| --- | --- |
| `h>=260 and w>=200` | Project + branch, activity, captioned bar, crab above. |
| `h>=160` | Percentage inline with the project, no caption. |
| `h>=110 and w>=140` | Crab beside a text column. |
| smaller | Crab only, plus a bar sliver if `h>=70`. |
| crab under `MIN_CRAB_HEIGHT` (44 px) | No crab at all — the phase word instead (`:812-821`). |

`_detail_for(height)` (`:669`) drops legs, brows and the highlight at `mid` and
`mini`.

## Testing it

Most coverage is on the **pose**, not pixels: sweep time and assert properties
(a blink happens; nothing jumps between frames; the alarm is louder than every
calm phase). Pixel tests run with `animate=False`, which pins `t=0.0` and makes
them time-independent. `tests/test_crab.py` also pins `_mix` against hardcoded
values so the blink schedule cannot silently change.

## See also

- [widgets.md](widgets.md) — the registry and how a widget is wired in.
- [../sessions/normalize.md](../sessions/normalize.md) — where phases come from.
- [../architecture/frame-budget.md](../architecture/frame-budget.md) — the measurements.
