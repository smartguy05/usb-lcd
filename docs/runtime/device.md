# device.py — the wire to a panel

> **Covers:** `src/usb_lcd_dashboard/device.py`, `src/usb_lcd_dashboard/turing_usb.py`

Defines the `PanelDevice` protocol and its three implementations: the real
Turing serial panel, a file-writing simulator, and a deliberately unimplemented
stub for the ultra-wide. It owns how pixels physically leave the process and
knows nothing about diffing or scheduling.

## The protocol

`PanelDevice` (`device.py:27`, `@runtime_checkable`):

| Member | Line | Contract |
| --- | --- | --- |
| `size`, `device` | `:28-29` | Attributes, not methods. |
| `open()` | `:31` | May discover the real device path. |
| `close()` | `:33` | **Must tolerate never having opened.** |
| `write(image, pos=(0, 0))` | `:35` | `pos` is the top-left of a partial write. |
| `supports_partial() -> bool` | `:37` | Whether `write` honours `pos`. |
| `health_check()` | `:39` | Raise if the link is no longer the one we opened. |

`make_device(config, simulate=False)` (`device.py:161`) is the single mapping
from `display.kind` to a class. A new kind must be added **both** here and to
`DISPLAY_KINDS` in [config.md](config.md), or the config will validate and then
fail at connect time.

## SerialPanel

`device.py:42`. The 3.5" Turing/UsbMonitor panel over its CDC-ACM bridge,
`LEGACY_SIZE = (480, 320)` (`device.py:23`).

- `__init__` refuses a config whose size is not `LEGACY_SIZE` (`:46-51`) — early,
  at construction, not at open time.
- On POSIX a non-`AUTO` device that does not exist raises `FileNotFoundError`
  before the driver is touched (`:63-64`).
- The driver is constructed with the panel's **native portrait** dimensions
  (`display_width=320, display_height=480`); landscape is then a rotation on top
  (`:65-66`). `self.device` is reassigned from `lcd.com_port` after open, which
  is how `AUTO` resolves to a real port.
- `supports_partial()` is `True`.

### `health_check` exists because the driver lies

Quoted from `device.py:98-106`:

> smartscreen_driver swallows a SerialException by closing the port, reopening
> it and retrying the write. It does not replay
> initialize_comm/screen_on/set_brightness/set_orientation, so the panel comes
> back in its default orientation with a cleared framebuffer while our handle
> still looks healthy. Unplugging the display triggers exactly this, and the
> stale diff base then paints crops at the wrong offsets.

The mechanism is object identity: `serial_handle` is captured once in `open()`,
and if `lcd.lcd_serial` is no longer the *same object*, the port was silently
reopened and `health_check` raises `ConnectionError` (`:107-110`). This is the
only way to notice, because every other signal still looks fine.

## SimulatedPanel

`device.py:113`. Saves the frame to `screencap.png` (path is a constructor
argument). `open`/`close`/`health_check` are no-ops.

`supports_partial()` returns **False on purpose** (`:135-137`): *"A crop saved on
its own would be a file of just that crop."* There is no framebuffer to paint
into, so a partial write would silently corrupt the preview.

This is what makes the ultra-wide layout developable without the hardware — see
[../architecture/overview.md](../architecture/overview.md).

## WindowPanel

`device.py:143`. `__init__` always raises `NotImplementedError`. This is a loud
stub, not an unfinished TODO: the ultra-wide panel's transport is genuinely
unknown, and even if it turns out to be a monitor, the embeddable CPython the
Windows installer bundles ships no tkinter, so `ImageTk` is unavailable. Both
open questions are recorded in the class docstring (`:144-151`).

## Tests

`tests/test_device.py` — kind-to-class mapping including `auto` and the
`simulate` override, the size guard, the window stub, unknown kinds, and the
simulator's whole-frame-only behaviour.

## See also

- [display.md](display.md) — the only caller.
- [config.md](config.md) — `DISPLAY_KINDS`, `device`, `orientation`, `brightness`.
- [../packaging/linux.md](../packaging/linux.md#the-udev-rule) — what creates `/dev/turing-lcd`.
