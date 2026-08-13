import pytest
from PIL import Image

from usb_lcd_dashboard.config import Config
from usb_lcd_dashboard.display import Display


class FakePanel:
    """Stands in for a transport, including the failure the real one has.

    smartscreen_driver reopens its own serial port on a write error without
    replaying the panel's initialisation, which is what reopen() models.
    """

    def __init__(self, size=(480, 320), partial=True):
        self.size = size
        self.device = "FAKE"
        self.calls = []
        self.partial = partial
        self.healthy = True
        self.opened = False

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def write(self, image, pos=(0, 0)):
        self.calls.append((image.size, pos))

    def supports_partial(self):
        return self.partial

    def health_check(self):
        if not self.healthy:
            raise ConnectionError("serial port was reopened by the driver")

    def reopen(self):
        self.healthy = False


def _display(**kwargs) -> Display:
    display = Display(Config(), panel=FakePanel(**kwargs))
    display.connect()
    return display


def _frame(colour: str, size=(480, 320)) -> Image.Image:
    return Image.new("RGB", size, colour)


def test_first_frame_is_always_a_full_paint():
    display = _display()
    assert display.paint(_frame("black"))
    assert display.panel.calls == [((480, 320), (0, 0))]


def test_unchanged_frame_is_not_repainted():
    display = _display()
    display.paint(_frame("black"))
    assert display.paint(_frame("black")) is False
    assert len(display.panel.calls) == 1


def test_a_small_change_is_sent_as_a_crop():
    display = _display()
    display.paint(_frame("black"))
    frame = _frame("black")
    frame.paste(Image.new("RGB", (20, 20), "white"), (100, 100))
    assert display.paint(frame)
    assert display.panel.calls[-1] == ((20, 20), (100, 100))


def test_a_large_change_is_promoted_to_a_full_frame():
    display = _display()
    display.paint(_frame("black"))
    assert display.paint(_frame("white"))
    assert display.panel.calls[-1] == ((480, 320), (0, 0))


def test_a_panel_without_partial_support_always_gets_the_whole_frame():
    display = _display(partial=False)
    display.paint(_frame("black"))
    frame = _frame("black")
    frame.paste(Image.new("RGB", (20, 20), "white"), (100, 100))
    assert display.paint(frame)
    assert display.panel.calls == [((480, 320), (0, 0)), ((480, 320), (0, 0))]


def test_a_reopened_port_is_reported_so_the_daemon_reconnects():
    display = _display()
    display.paint(_frame("black"))
    display.panel.reopen()
    with pytest.raises(ConnectionError):
        display.paint(_frame("white"))


def test_a_reopened_port_keeps_the_diff_base_so_the_next_paint_is_full():
    display = _display()
    display.paint(_frame("black"))
    base = display.previous

    # The driver reopens the port while this write is in flight.
    original = display.panel.write

    def write_then_reopen(image, pos=(0, 0)):
        original(image, pos)
        display.panel.reopen()

    display.panel.write = write_then_reopen
    with pytest.raises(ConnectionError):
        display.paint(_frame("white"))
    assert display.previous is base, "a reset panel must not become the diff base"


def test_painting_before_connecting_is_an_error():
    display = Display(Config(), panel=FakePanel())
    with pytest.raises(ConnectionError):
        display.paint(_frame("black"))


def test_a_healthy_panel_reports_connected_and_its_own_size():
    display = _display(size=(1920, 462))
    assert display.connected
    assert display.size == (1920, 462)
    assert display.device == "FAKE"
    display.close()
    assert display.connected is False
