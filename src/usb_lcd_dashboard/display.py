from __future__ import annotations

import logging

from PIL import Image, ImageChops

from .config import Config
from .device import PanelDevice, make_device

LOG = logging.getLogger(__name__)


class Display:
    """Decides what to send to a panel, and how little of it.

    The transport lives behind a PanelDevice; what stays here is the dirty-rect
    diffing, which is transport-independent and hard-won.
    """

    def __init__(
        self,
        config: Config,
        simulate: bool = False,
        panel: PanelDevice | None = None,
    ):
        self.config = config
        self.simulate = simulate
        self.panel = panel
        self.opened = False
        self.device = config.device
        self.previous: Image.Image | None = None
        if panel is not None:
            self.device = panel.device

    @property
    def size(self) -> tuple[int, int]:
        return self.panel.size if self.panel is not None else self.config.size

    @property
    def connected(self) -> bool:
        return self.opened

    def connect(self) -> None:
        panel = self.panel or make_device(self.config, simulate=self.simulate)
        panel.open()
        self.panel = panel
        self.device = panel.device
        self.opened = True
        self.previous = None

    def close(self) -> None:
        # Not gated on self.opened: the daemon calls close() after a failed
        # connect(), and a panel that got half-way through opening still has a
        # port to release. Every panel's close() tolerates never having opened.
        if self.panel is not None:
            try:
                self.panel.close()
            finally:
                self.opened = False
        else:
            self.opened = False

    def paint(self, image: Image.Image, force: bool = False) -> bool:
        if self.panel is None or not self.opened:
            raise ConnectionError("display is not connected")
        self.panel.health_check()

        bbox = (
            None
            if self.previous is None
            else ImageChops.difference(self.previous, image).getbbox()
        )
        if not force and self.previous is not None and bbox is None:
            return False
        if force or self.previous is None or not self.panel.supports_partial():
            self.panel.write(image)
            LOG.info("LCD full frame written: %sx%s", image.width, image.height)
        else:
            assert bbox is not None
            left, top, right, bottom = bbox
            area = (right - left) * (bottom - top)
            if area > image.width * image.height * 0.7:
                self.panel.write(image)
                LOG.debug("LCD full frame written after large diff")
            else:
                self.panel.write(image.crop(bbox), pos=(left, top))
                LOG.debug("LCD partial frame written: %s", bbox)
        try:
            self.panel.health_check()
        except ConnectionError:
            # The write above went to a panel that has since been reset. Leave
            # self.previous alone so the reconnect repaints a full frame.
            raise
        self.previous = image.copy()
        return True
