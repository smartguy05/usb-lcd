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


def test_the_serial_panel_accepts_the_portrait_logical_canvas():
    config = replace(LEGACY, width=320, height=480, orientation="portrait")
    panel = make_device(config)
    assert isinstance(panel, SerialPanel)
    assert panel.size == (320, 480)


def test_serial_partial_writes_are_mapped_for_a_flipped_mount():
    panel = SerialPanel(replace(LEGACY, orientation="landscape_flipped"))
    calls = []

    class Lcd:
        def paint(self, image, pos=(0, 0)):
            calls.append((image.copy(), pos))

    panel.lcd = Lcd()
    crop = Image.new("RGB", (2, 1))
    crop.putpixel((0, 0), (255, 0, 0))
    crop.putpixel((1, 0), (0, 0, 255))
    panel.write(crop, (10, 20))
    assert calls[0][1] == (468, 299)
    assert calls[0][0].getpixel((0, 0)) == (0, 0, 255)


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


# --------------------------------------------------- auto picks a transport


def test_auto_picks_the_usb_panel_for_a_turzx_size():
    """1920x462 is a TURZX panel, and "auto" has to reach it.

    Before this, "auto" was a synonym for the serial panel, so a wide panel
    configured with it sat waiting on a serial port that never appears.
    """
    panel = make_device(replace(WIDE, display_kind="auto"))
    assert isinstance(panel, TuringUsbPanel)


def test_auto_rejects_a_size_no_panel_has():
    with pytest.raises(ValueError) as excinfo:
        make_device(replace(Config(), display_kind="auto", width=1234, height=567))
    # The message has to name the size, because the fix is in the config file.
    assert "1234x567" in str(excinfo.value)


def test_auto_does_not_probe_the_bus():
    """The size decides, so an absent panel still resolves to the right class.

    A KVM can have the panel on the other machine at daemon start; picking the
    transport by probing would latch the wrong one for the life of the process.
    """
    panel = make_device(replace(WIDE, display_kind="auto"))
    assert isinstance(panel, TuringUsbPanel)
    assert panel.usb is None


# ------------------------------------------------- the USB panel disconnects


class _GoneDevice:
    """A pyusb device whose panel has left the bus."""

    def __init__(self, error):
        self._error = error

    def ctrl_transfer(self, *args, **kwargs):
        raise self._error


def test_usb_health_check_reports_a_panel_that_left_the_bus():
    import usb.core

    panel = TuringUsbPanel(WIDE)
    panel.usb = _GoneDevice(usb.core.USBError("No such device"))
    # ConnectionError specifically: Display only reconnects on that.
    with pytest.raises(ConnectionError):
        panel.health_check()


def test_usb_health_check_is_quiet_before_open():
    assert TuringUsbPanel(WIDE).health_check() is None


def test_usb_write_turns_a_vanished_panel_into_a_disconnection(monkeypatch):
    import usb.core

    from usb_lcd_dashboard import turing_usb

    panel = TuringUsbPanel(WIDE)
    panel.usb = object()

    def explode(device, image):
        raise usb.core.USBError("No such device")

    monkeypatch.setattr(turing_usb, "send_image", explode)
    with pytest.raises(ConnectionError):
        panel.write(Image.new("RGB", panel.size))
