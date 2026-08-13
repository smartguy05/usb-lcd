# The frame budget

Why the panel updates as slowly as it does, and what that forces on anything
that moves. Every number here was measured on the hardware, not estimated.

## The chain

Three things gate a frame, in order:

1. **The loop.** `poll_timeout` bounds how long the daemon blocks waiting for an
   event; it then sleeps the remainder of the frame. A hardcoded 0.2 s here used
   to cap the panel at 5 fps regardless of `refresh_hz`. It now follows the
   frame interval — [transport.md](../runtime/transport.md#poll_timeout-is-the-real-frame-rate-floor).
2. **Compose.** Drawing a crab tile costs a few milliseconds; supersampled,
   2.5–5 ms for realistic sizes. Not the bottleneck.
3. **The wire.** A 115200-baud CDC serial link. How long a frame takes is set by
   **how many pixels changed**, because `Display.paint` sends only the changed
   rectangle.

On the 3.5" panel the wire wins by an order of magnitude.

## Measurements

On the real 480×320 Turing panel, full-tile crab:

| Situation | Dirty area | Result |
| --- | --- | --- |
| Crab redrawing its own box | ~27% of the panel | **2.2–2.4 fps** |
| Same, plus a pulsing border | 100% (the border is at the edge) | **0.8 fps** |

Raising `refresh_hz` from 2 to 8 is worth about **0.4 fps** — it shrinks the
poll timeout, nothing more. The wire is the ceiling.

Supersampling cost, 300×220 output, measured with Pillow 12.3:

| Downscale | 2× | 3× | 4× |
| --- | --- | --- | --- |
| `resize(LANCZOS)` | 8.3 ms | 13.2 ms | 21.0 ms |
| **`reduce()`** | **2.1 ms** | **4.2 ms** | **6.0 ms** |

`reduce()` is an exact integer box filter — the correct answer for
supersampling, about twice as fast, and it does not ring around the dark pupil
the way LANCZOS does.

## What this forces

- **Nothing oscillates above ~0.63 Hz.** A wave needs roughly four samples per
  cycle to read as a wave. At 2.4 fps that puts the ceiling near 0.6 Hz. Faster
  is not merely wasted — it aliases, and the claws appear to teleport.
- **Nothing animates at a tile's outer edge.** The diff is a single union
  bounding box, so a breathing border dirties the whole tile every frame. It
  costs three times the bytes at the one moment responsiveness matters, and at
  1.4 s per frame a 0.62 s pulse is slower than the frame rate and reads as
  random flicker. The alarm border is a solid slab for exactly this reason.
- **Two animated tiles at opposite ends of a wide panel** union into a
  near-full-width rect and fall back to full-frame writes. Theoretical today —
  the ultra-wide's transport is unsettled — but it is the reason the diff is
  worth understanding before adding a second animated widget.

## If the ultra-wide ever works

None of the 0.63 Hz ceiling is inherent to the widgets; it is a property of a
115200-baud link. A faster transport would allow smoother motion, but the
constants live in `_oscillators` (`crab.py:151`) and the reasoning is recorded
there — change them together with the comment, not separately.

## See also

- [../runtime/display.md](../runtime/display.md) — the diffing that produces these numbers.
- [../rendering/crab.md](../rendering/crab.md) — the widget designed around them.
- [invariants.md](invariants.md)
