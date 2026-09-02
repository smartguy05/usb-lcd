# active_background.py — the animated wallpaper layer

> **Covers:** `src/usb_lcd_dashboard/active_background.py`

A red fox that runs across the whole panel *behind* the tiles, exits one edge,
dwells off-screen, then re-enters from the other side. Its speed follows live CPU
usage. This is the one moving thing that is **not** a widget: a tile is a pure
function of `ctx.now`, but a position that is the integral of a *varying* speed
must be carried between frames, so this layer is stateful and stepped by the
daemon, then composited under the tiles.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `ActiveBackground` | `active_background.py:82` | The stateful fox runner. |
| `ActiveBackground.step(dt, size)` | `active_background.py:126` | Advance by `dt`; return this frame's full-panel overlay, or `None` while off-screen. |
| `ActiveBackground.reconfigure(cfg)` | `active_background.py:99` | Adopt edited settings without resetting position. |
| `_load_raw_frames()` | `active_background.py:50` | The run-cycle PNGs as RGBA; `[]` if missing. |
| `_cpu_fraction()` | `active_background.py:68` | Live CPU in 0..1; neutral `0.5` without psutil. |
| `DWELL_SECONDS` | `active_background.py:34` | Off-screen pause between runs. |

## How it fits together

- **Config.** `ActiveBackgroundConfig` (`config.py:56`) holds `enabled`, `scale`,
  `speed_min`, `speed_max`, `opacity`; `_parse_active_background`
  (`config.py:400`) reads the `[active_background]` table, absent → `None` → off.
- **Compose.** `compose(...)` takes an `active_background` overlay
  (`layout.py:175`), painted over the wallpaper and under every tile; its
  presence disables the byte-identical full-screen fast path.
- **Daemon.** The daemon owns one `ActiveBackground`, built or reconfigured in
  `_apply_config`, and steps it with a clamped wall-clock delta each frame
  outside the screen saver, passing the overlay to `compose`.

## Degradation

Missing psutil → neutral speed; missing or unreadable sprites → the layer draws
nothing. Neither takes the panel down, matching the "failures degrade" invariant.

## Art

Six-frame run cycle under `assets/fox/`, baked by `tools/make_fox_sprites.py`.
The fox faces right; the runtime flips it for the return direction. Replace the
frames with your own equal-height RGBA `run_XX.png` files to change the animal.
