# device.py — the wire to a panel

> **Covers:** `src/usb_lcd_dashboard/device.py`, `src/usb_lcd_dashboard/turing_usb.py`, `src/usb_lcd_dashboard/orientation.py`

Defines the `PanelDevice` protocol and its four implementations: the 3.5" Turing
serial panel, current-generation TURZX panels over native USB, a file-writing
simulator, and a deliberately unimplemented stub for a panel the OS enumerates
as a monitor. It owns how pixels physically leave the process and knows nothing
about diffing or scheduling.

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

`make_device(config, simulate=False)` (`device.py:268`) is the single mapping
from `display.kind` to a class. A new kind must be added **both** here and to
`DISPLAY_KINDS` in [config.md](config.md), or the config will validate and then
fail at connect time.

### `auto` decides on size, not by probing

`_autodetect` (`device.py:245`) maps the configured size to a transport:
`LEGACY_SIZE` is the serial panel, anything in `turing_usb.py:PRODUCT_SIZES` is
a USB one, and any other size is a `ValueError` naming it.

It deliberately does **not** look at the bus. The panel can be absent when the
daemon starts — a KVM with the panel on the other machine, or simply not plugged
in yet — and a probe would then pick the wrong transport and stay wrong for the
life of the process. The size is unambiguous, so it is the better signal.

`auto` at the default 480x320 is still the serial panel, which is what
`tests/test_device.py` has always pinned.

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

### Four mounting orientations

The renderer and preview use logical, viewer-upright coordinates. The shared
orientation helpers normalize portrait dimensions, rotate full images, and map
partial crop origins into the panel's canonical landscape buffer. The serial
driver therefore stays in hardware landscape while software supports
`landscape`, `portrait`, and both flipped variants consistently. A portrait
3.5-inch canvas is 320x480; its normalized hardware size remains 480x320.

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

## TuringUsbPanel

`device.py:143`. Current-generation TURZX panels (`1CBE:*`), including the 9.2"
1920x462 unit (`0x0092`). These are **not** serial: they enumerate as a single
vendor-class interface with no kernel driver, so libusb talks to `/dev/bus/usb`
directly and there is no tty to open. `turing_usb.py` carries the protocol —
DES-encrypted commands and a JPEG framebuffer upload.

- `open()` finds the device, checks its size against the config, and sets
  brightness. `self.device` becomes a label like `USB 1CBE:0092`, not a path.
- `supports_partial()` is **False**: every write is a whole frame.
- `write()` rotates into the panel's native portrait buffer, and translates a
  `usb.core.USBError` into `ConnectionError` — a panel that left mid-frame is a
  disconnection, and `Display` only reconnects on `ConnectionError`.
- `health_check()` issues an 18-byte `GET_DESCRIPTOR`. This is the *only*
  detector when the frame is unchanged and `write` is never reached, which
  matters because the daemon's connected state drives the tray icon.
  `get_active_configuration` would not do: pyusb caches it after `open()` and
  keeps answering happily for a panel that is long gone.

On Linux the raw node is root-only until the packaged udev rule tags it; see
[../packaging/linux.md](../packaging/linux.md#the-udev-rule).

## WindowPanel

`device.py:227`. `__init__` always raises `NotImplementedError`. This is a loud
stub, not an unfinished TODO: whether any panel here is a monitor is unsettled,
and even if one is, the embeddable CPython the Windows installer bundles ships
no tkinter, so `ImageTk` is unavailable. Both open questions are recorded in the
class docstring.

## Tests

`tests/test_device.py` — kind-to-class mapping including `auto` (both the legacy
size and a TURZX one, plus the size it rejects) and the `simulate` override, the
size guard, the window stub, unknown kinds, the simulator's whole-frame-only
behaviour, and the USB panel turning a vanished device into a `ConnectionError`
from both `write` and `health_check`.

## See also

- [display.md](display.md) — the only caller.
- [config.md](config.md) — `DISPLAY_KINDS`, `device`, `orientation`, `brightness`.
- [../packaging/linux.md](../packaging/linux.md#the-udev-rule) — panel access for both transports.
