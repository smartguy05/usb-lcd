# screensaver.py — idle protection

> **Covers:** `src/usb_lcd_dashboard/screensaver.py`

`render_screensaver(size, now)` returns an RGB frame with a clock on pure black.
Its position is derived from the UTC minute using co-prime steps, so it changes
only once per minute, needs no mutable renderer state, and is reproducible in a
test. Identical intervening frames are suppressed by `Display.paint`.

The daemon owns inactivity. It starts at process launch, resets for accepted
Claude/Codex events and changed visible message, notification, or todo content,
and uses `[screensaver].idle_seconds` as the deadline. The preview receives the
same saver frame even when no panel is connected.

Tests: `tests/test_screensaver.py` and the screen-saver cases in
`tests/test_daemon.py`.
