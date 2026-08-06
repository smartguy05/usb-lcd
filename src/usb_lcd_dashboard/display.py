from __future__ import annotations

import logging
import os
from pathlib import Path

from PIL import Image, ImageChops

from .config import Config

LOG = logging.getLogger(__name__)


class Display:
    def __init__(self, config: Config, simulate: bool = False):
        self.config = config
        self.simulate = simulate
        self.lcd = None
        self.device = config.device
        self.previous: Image.Image | None = None

    @property
    def connected(self) -> bool:
        return self.simulate or self.lcd is not None

    def connect(self) -> None:
        if self.simulate:
            return
        from smartscreen_driver.lcd_comm import Orientation
        from smartscreen_driver.lcd_comm_rev_a import LcdCommRevA

        device = self.config.device or "AUTO"
        if (
            os.name != "nt"
            and device.upper() != "AUTO"
            and not Path(device).exists()
        ):
            raise FileNotFoundError(device)
        lcd = LcdCommRevA(
            com_port=device,
            display_width=320,
            display_height=480,
        )
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
        self.previous = None

    def close(self) -> None:
        if self.lcd is not None:
            try:
                self.lcd.close_serial()
            finally:
                self.lcd = None

    def paint(self, image: Image.Image, force: bool = False) -> bool:
        if self.simulate:
            image.save("screencap.png")
            self.previous = image.copy()
            return True
        if self.lcd is None:
            raise ConnectionError("display is not connected")

        bbox = (
            None
            if self.previous is None
            else ImageChops.difference(self.previous, image).getbbox()
        )
        if not force and self.previous is not None and bbox is None:
            return False
        if force or self.previous is None:
            self.lcd.paint(image)
            LOG.info("LCD full frame written: %sx%s", image.width, image.height)
        else:
            assert bbox is not None
            left, top, right, bottom = bbox
            area = (right - left) * (bottom - top)
            if area > image.width * image.height * 0.7:
                self.lcd.paint(image)
                LOG.debug("LCD full frame written after large diff")
            else:
                self.lcd.paint(image.crop(bbox), pos=(left, top))
                LOG.debug("LCD partial frame written: %s", bbox)
        self.previous = image.copy()
        return True

