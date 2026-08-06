import pytest
from PIL import Image

from usb_lcd_dashboard.config import Config
from usb_lcd_dashboard.display import Display


class FakeSerial:
    pass


class FakeLcd:
    """Stands in for smartscreen_driver, which reopens its own serial port on a
    write error without replaying the panel's initialisation."""

    def __init__(self):
        self.calls = []
        self.lcd_serial = FakeSerial()

    def paint(self, image, pos=(0, 0)):
        self.calls.append((image.size, pos))

    def reopen(self):
        self.lcd_serial = FakeSerial()


def _display() -> Display:
    display = Display(Config())
    display.lcd = FakeLcd()
    display.serial_handle = display.lcd.lcd_serial
    return display


def _frame(colour: str) -> Image.Image:
    return Image.new("RGB", (480, 320), colour)


def test_first_frame_is_always_a_full_paint():
    display = _display()
    assert display.paint(_frame("black"))
    assert display.lcd.calls == [((480, 320), (0, 0))]


def test_unchanged_frame_is_not_repainted():
    display = _display()
    display.paint(_frame("black"))
    assert display.paint(_frame("black")) is False
    assert len(display.lcd.calls) == 1


def test_a_reopened_port_is_reported_so_the_daemon_reconnects():
    display = _display()
    display.paint(_frame("black"))
    display.lcd.reopen()
    with pytest.raises(ConnectionError):
        display.paint(_frame("white"))


def test_a_reopened_port_keeps_the_diff_base_so_the_next_paint_is_full():
    display = _display()
    display.paint(_frame("black"))
    base = display.previous

    # The driver reopens the port while this write is in flight.
    original = display.lcd.paint

    def paint_then_reopen(image, pos=(0, 0)):
        original(image, pos)
        display.lcd.reopen()

    display.lcd.paint = paint_then_reopen
    with pytest.raises(ConnectionError):
        display.paint(_frame("white"))
    assert display.previous is base, "a reset panel must not become the diff base"


def test_connect_records_the_serial_handle_it_initialised():
    display = Display(Config())
    assert display._driver_reopened() is False
