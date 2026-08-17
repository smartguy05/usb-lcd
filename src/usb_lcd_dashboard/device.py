"""Panel transports.

Display owns the dirty-rect diffing that decides *what* to send; a PanelDevice
owns *how* it goes out. Older Turing panels use a serial protocol. Current TURZX
panels use native USB and accept encrypted commands plus PNG/JPEG frames.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image

from .config import Config

LOG = logging.getLogger(__name__)

LEGACY_SIZE = (480, 320)


@runtime_checkable
class PanelDevice(Protocol):
    size: tuple[int, int]
    device: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def write(self, image: Image.Image, pos: tuple[int, int] = (0, 0)) -> None: ...

    def supports_partial(self) -> bool: ...

    def health_check(self) -> None: ...


class SerialPanel:
    """The Turing/UsbMonitor 3.5" panel over its CDC-ACM serial bridge."""

    def __init__(self, config: Config):
        if config.size != LEGACY_SIZE:
            raise ValueError(
                f"display.kind={config.display_kind!r} drives a "
                f"{LEGACY_SIZE[0]}x{LEGACY_SIZE[1]} panel, but the config asks for "
                f"{config.width}x{config.height}"
            )
        self.config = config
        self.size = LEGACY_SIZE
        self.device = config.device
        self.lcd = None
        self.serial_handle = None

    def open(self) -> None:
        from smartscreen_driver.lcd_comm import Orientation
        from smartscreen_driver.lcd_comm_rev_a import LcdCommRevA

        device = self.config.device or "AUTO"
        if os.name != "nt" and device.upper() != "AUTO" and not Path(device).exists():
            raise FileNotFoundError(device)
        # The driver takes the panel's native portrait dimensions; LANDSCAPE then
        # gives the 480x320 canvas everything else is drawn against.
        lcd = LcdCommRevA(com_port=device, display_width=320, display_height=480)
        lcd.initialize_comm()
        lcd.screen_on()
        lcd.set_brightness(self.config.brightness)
        orientation = (
            Orientation.LANDSCAPE
            if self.config.orientation == "landscape"
            else Orientation.PORTRAIT
        )
        lcd.set_orientation(orientation)
        self.device = lcd.com_port
        self.lcd = lcd
        self.serial_handle = getattr(lcd, "lcd_serial", None)

    def close(self) -> None:
        if self.lcd is not None:
            try:
                self.lcd.close_serial()
            finally:
                self.lcd = None
                self.serial_handle = None

    def write(self, image: Image.Image, pos: tuple[int, int] = (0, 0)) -> None:
        if self.lcd is None:
            raise ConnectionError("display is not connected")
        self.lcd.paint(image, pos=pos)

    def supports_partial(self) -> bool:
        return True

    def health_check(self) -> None:
        """Did the driver silently replace the serial port under us?

        smartscreen_driver swallows a SerialException by closing the port,
        reopening it and retrying the write. It does not replay
        initialize_comm/screen_on/set_brightness/set_orientation, so the panel
        comes back in its default orientation with a cleared framebuffer while
        our handle still looks healthy. Unplugging the display triggers exactly
        this, and the stale diff base then paints crops at the wrong offsets.
        """
        if self.lcd is None or self.serial_handle is None:
            return
        if getattr(self.lcd, "lcd_serial", None) is not self.serial_handle:
            raise ConnectionError("serial port was reopened by the driver")


class SimulatedPanel:
    """Writes the frame to screencap.png instead of a panel.

    This is what makes a layout for hardware that has not arrived developable:
    any frame size works, and the whole compose path runs for real.
    """

    def __init__(self, config: Config, path: str = "screencap.png"):
        self.config = config
        self.size = config.size
        self.device = path
        self.path = path

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def write(self, image: Image.Image, pos: tuple[int, int] = (0, 0)) -> None:
        image.save(self.path)

    def supports_partial(self) -> bool:
        # A crop saved on its own would be a file of just that crop.
        return False

    def health_check(self) -> None:
        return None


class TuringUsbPanel:
    """TURZX native-USB panels, including the 1CBE:0092 9.2-inch model."""

    def __init__(self, config: Config):
        self.config = config
        self.size = config.size
        self.device = "AUTO"
        self.usb = None
        self.product_id = None

    def open(self) -> None:
        import usb.util

        from .turing_usb import PRODUCT_SIZES, find_device, send_command

        usb_device, product_id = find_device()
        native_size = PRODUCT_SIZES[product_id]
        if self.config.size != native_size:
            usb.util.dispose_resources(usb_device)
            raise ValueError(
                f"TURZX USB {product_id:04x} is {native_size[0]}x{native_size[1]}, "
                f"but the config asks for {self.config.width}x{self.config.height}"
            )
        send_command(usb_device, 10)  # synchronize
        send_command(usb_device, 14, bytes((round(self.config.brightness / 100 * 102),)))
        self.usb = usb_device
        self.product_id = product_id
        self.device = f"USB {0x1CBE:04X}:{product_id:04X}"

    def close(self) -> None:
        if self.usb is not None:
            import usb.util

            usb.util.dispose_resources(self.usb)
            self.usb = None

    def write(self, image: Image.Image, pos: tuple[int, int] = (0, 0)) -> None:
        if self.usb is None:
            raise ConnectionError("display is not connected")
        if pos != (0, 0) or image.size != self.size:
            raise ValueError("TURZX USB panels require full-frame writes")
        from .turing_usb import send_image

        # The USB protocol always consumes the panel's native portrait buffer.
        if self.config.orientation == "landscape":
            image = image.transpose(Image.Transpose.ROTATE_270)
        else:
            image = image.transpose(Image.Transpose.ROTATE_180)
        send_image(self.usb, image)

    def supports_partial(self) -> bool:
        return False

    def health_check(self) -> None:
        return None


class WindowPanel:
    """A panel the OS enumerates as a monitor. Not implemented yet.

    Whether the 9.2" ultra-wide is this or another serial protocol cannot be
    settled from its manual, which carries no protocol, driver or USB id at all.
    Two things to resolve when the hardware lands: which of the two it is, and —
    if it is a monitor — what draws the window, since the embeddable CPython the
    Windows installer bundles ships no tkinter, so ImageTk is unavailable.
    """

    def __init__(self, config: Config):
        raise NotImplementedError(
            'display.kind="window" is not implemented yet: the panel\'s transport '
            "is unknown until the hardware arrives. Use kind=\"simulated\" to "
            "develop and preview the layout in the meantime."
        )


def make_device(config: Config, simulate: bool = False) -> PanelDevice:
    if simulate or config.display_kind == "simulated":
        return SimulatedPanel(config)
    if config.display_kind in ("turing_rev_a", "auto"):
        return SerialPanel(config)
    if config.display_kind == "turing_usb":
        return TuringUsbPanel(config)
    if config.display_kind == "window":
        return WindowPanel(config)
    raise ValueError(f"unknown display.kind: {config.display_kind!r}")
