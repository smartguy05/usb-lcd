# display.py — dirty-rect diffing

> **Covers:** `src/usb_lcd_dashboard/display.py`

Decides *what* to send to the panel and how little of it. The transport lives
behind a [`PanelDevice`](device.md); what stays here is the diffing, which is
transport-independent and, per the class docstring (`display.py:14-18`),
"hard-won".

This module is why the frame rate is what it is. See
[../architecture/frame-budget.md](../architecture/frame-budget.md).

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `Display(config, simulate=False, panel=None)` | `display.py:20` | `panel` is injectable for tests. |
| `.size` | `display.py:35` | The panel's own size if connected, else the configured size. |
| `.connected` | `display.py:39` | Alias of `opened`. |
| `.connect()` | `display.py:43` | Build via `make_device` if needed, open, **reset `previous`**. |
| `.close()` | `display.py:51` | Close the panel if there is one. |
| `.paint(image, force=False) -> bool` | `display.py:61` | Diff and write. Returns whether anything was written. |

## What `paint()` decides

1. `:62-63` Raise `ConnectionError` if not connected.
2. `:64` `panel.health_check()` **before** the work — catch a reset panel before
   wasting a diff.
3. `:66-69` `bbox = ImageChops.difference(previous, image).getbbox()`, or `None`
   when there is no previous frame.
4. `:71-72` Identical frame and not forced → return `False`. **Nothing is sent.**
5. `:73-85` Choose the write:
   - Full frame if forced, if there is no previous frame, or if
     `not panel.supports_partial()`.
   - Full frame if the changed area exceeds **70%** of the panel (`:80`).
   - Otherwise `panel.write(image.crop(bbox), pos=(left, top))`.
6. `:86-91` `health_check()` again, *after* the write.
7. `:92-93` `previous = image.copy()`; return `True`.

## Invariants

- **`connect()` always clears `previous`** (`:49`), so the first paint after any
  connection is a full frame. A partial crop against a framebuffer the panel
  never actually displayed would be garbage at the wrong offset.
- **The post-write `ConnectionError` must propagate, not be caught.**
  `display.py:88-91`: *"The write above went to a panel that has since been
  reset. Leave self.previous alone so the reconnect repaints a full frame."*
  Catching it here would leave a stale diff base and paint crops at wrong
  offsets forever. `tests/test_display.py::test_a_reopened_port_keeps_the_diff_base_so_the_next_paint_is_full`
  pins it.
- **`close()` is deliberately not gated on `opened`** (`:52-54`): *"the daemon
  calls close() after a failed connect(), and a panel that got half-way through
  opening still has a port to release."* Every `PanelDevice.close()` must
  tolerate never having opened.
- **The diff is a single union bounding box.** Two animated tiles at opposite
  ends of a wide panel union into a near-full-width rect and fall back to full
  frames. This is the reason a widget must not animate at its tile's outer edge
  — see [../rendering/crab.md](../rendering/crab.md#why-the-alarm-border-does-not-pulse).

## Tests

`tests/test_display.py`, using a `FakePanel` double: first frame is full, an
unchanged frame writes nothing, a small change is a crop, a large change is
promoted to full, a panel without partial support always gets the whole frame,
a reopened port is reported and keeps the diff base, painting before connecting
raises.

## See also

- [device.md](device.md) — the `PanelDevice` protocol and `health_check`.
- [daemon.md](daemon.md) — the caller.
- [../architecture/frame-budget.md](../architecture/frame-budget.md) — measured throughput.
