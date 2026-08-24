"""Hardware-selected display profiles for laptops that move between panels."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from serial.tools.list_ports import comports

from .config import Config, load_config, write_config
from .device import LEGACY_SIZE
from .orientation import native_size

LOG = logging.getLogger(__name__)
SERIAL_VID = 0x1A86
SERIAL_PID = 0x5722
SERIAL_NUMBER = "USB35INCHIPSV2"


@dataclass(frozen=True, slots=True)
class PanelIdentity:
    key: str
    kind: str
    size: tuple[int, int]
    device: str = "AUTO"


def detect_panel() -> PanelIdentity | None:
    """Return the supported panel currently visible to this machine."""
    try:
        from .turing_usb import PRODUCT_SIZES, VENDOR_ID, _backend
        import usb.core

        devices = usb.core.find(
            idVendor=VENDOR_ID, find_all=True, backend=_backend()
        ) or ()
        for device in devices:
            product = int(device.idProduct)
            if product in PRODUCT_SIZES:
                return PanelIdentity(
                    f"turzx-{product:04x}", "turing_usb", PRODUCT_SIZES[product]
                )
    except Exception as exc:
        LOG.debug("TURZX profile probe failed: %s", exc)

    for port in comports():
        if port.serial_number == SERIAL_NUMBER or (
            port.vid == SERIAL_VID and port.pid == SERIAL_PID
        ):
            return PanelIdentity("legacy-480x320", "turing_rev_a", LEGACY_SIZE, port.device)
    return None


def profile_key_for_config(config: Config) -> str | None:
    """Infer which known panel an existing single-file config describes."""
    size = native_size(config.size, config.orientation)
    if size == LEGACY_SIZE:
        return "legacy-480x320"
    try:
        from .turing_usb import PRODUCT_SIZES

        for product, product_size in PRODUCT_SIZES.items():
            if size == product_size:
                return f"turzx-{product:04x}"
    except ImportError:
        pass
    return None


class ProfileStore:
    """Persist visual configurations and activate the attached panel's copy."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.directory = config_path.parent / "profiles"
        self.active_key: str | None = None

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.toml"

    def save(self, key: str, config: Config) -> None:
        write_config(replace(config, display_kind="auto"), self.path_for(key))

    def save_active(self, config: Config) -> None:
        if self.active_key is not None:
            self.save(self.active_key, config)

    def activate(self, panel: PanelIdentity, current: Config) -> Config:
        if self.active_key == panel.key:
            return current

        # Preserve the profile that was on screen, or seed an existing
        # single-file installation before the first hardware-selected switch.
        if self.active_key is not None:
            self.save(self.active_key, current)
        else:
            inferred = profile_key_for_config(current)
            if inferred is not None and not self.path_for(inferred).exists():
                self.save(inferred, current)

        target = self.path_for(panel.key)
        if target.exists():
            selected = load_config(target)
        else:
            # A newly encountered panel starts with the user's shared settings
            # and a safe full-canvas legacy dashboard; the editor can customize
            # it once and subsequent visits restore that exact result.
            from .layout import Tile

            selected = replace(
                current,
                display_kind="auto",
                device="AUTO",
                width=panel.size[0],
                height=panel.size[1],
                orientation="landscape",
                background=None,
                tiles=(Tile("legacy", 0, 0, panel.size[0], panel.size[1]),),
            )
            self.save(panel.key, selected)

        selected = replace(selected, display_kind="auto")
        write_config(selected, self.config_path)
        self.active_key = panel.key
        LOG.info("Activated display profile %s (%sx%s)", panel.key, *panel.size)
        return selected

