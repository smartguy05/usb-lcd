from dataclasses import replace

import pytest
from PIL import Image

from usb_lcd_dashboard.config import Config
from usb_lcd_dashboard.device import (
    SerialPanel,
    SimulatedPanel,
    TuringUsbPanel,
    make_device,
)
from usb_lcd_dashboard.turing_usb import _command


LEGACY = Config()
WIDE = replace(Config(), display_kind="simulated", width=1920, height=462)


def test_the_default_config_gets_the_serial_panel():
    panel = make_device(LEGACY)
    assert isinstance(panel, SerialPanel)
    assert panel.size == (480, 320)


def test_auto_is_also_the_serial_panel():
    assert isinstance(make_device(replace(LEGACY, display_kind="auto")), SerialPanel)


def test_simulate_overrides_the_configured_kind():
    assert isinstance(make_device(LEGACY, simulate=True), SimulatedPanel)


def test_the_simulated_kind_needs_no_flag():
    panel = make_device(WIDE)
    assert isinstance(panel, SimulatedPanel)
    assert panel.size == (1920, 462)


def test_the_turing_usb_kind_gets_the_native_usb_panel():
    config = replace(WIDE, display_kind="turing_usb")
    panel = make_device(config)
    assert isinstance(panel, TuringUsbPanel)
    assert panel.size == (1920, 462)


def test_turing_usb_commands_are_fixed_512_byte_packets():
    packet = _command(10)
    assert len(packet) == 512
    assert packet[-2:] == b"\xa1\x1a"


def test_the_serial_panel_refuses_a_size_it_cannot_drive():
    """Pointing a 1920x462 layout at the 3.5" panel must fail readably."""
    config = replace(LEGACY, width=1920, height=462)
    with pytest.raises(ValueError, match="1920x462"):
        make_device(config)


def test_the_window_kind_is_an_explicit_stub():
    config = replace(WIDE, display_kind="window")
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        make_device(config)


def test_an_unknown_kind_is_rejected():
    config = replace(LEGACY)
    object.__setattr__(config, "display_kind", "plasma")
    with pytest.raises(ValueError, match="unknown display.kind"):
        make_device(config)


def test_the_simulated_panel_writes_the_whole_frame_to_a_file(tmp_path):
    target = tmp_path / "screencap.png"
    panel = SimulatedPanel(WIDE, path=str(target))
    panel.open()
    panel.write(Image.new("RGB", (1920, 462), "#081018"))
    panel.health_check()
    panel.close()
    with Image.open(target) as saved:
        assert saved.size == (1920, 462)


def test_the_simulated_panel_does_not_do_partial_writes():
    """A crop saved on its own would be a file of just that crop."""
    assert SimulatedPanel(WIDE).supports_partial() is False
