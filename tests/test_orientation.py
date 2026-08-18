from PIL import Image

from usb_lcd_dashboard.orientation import (
    native_size,
    native_write,
    rotate_layout,
    rotate_rect,
)


def test_layout_rotation_swaps_the_canvas_and_preserves_rectangles():
    size, rects = rotate_layout(
        (480, 320), [(10, 20, 30, 40)], "landscape", "portrait"
    )
    assert size == (320, 480)
    assert rects == [(260, 10, 40, 30)]


def test_four_quarter_turns_restore_a_rectangle():
    rect = (11, 23, 37, 41)
    size = (480, 320)
    current = rect
    current_size = size
    for _ in range(4):
        current = rotate_rect(current, current_size, 1)
        current_size = current_size[::-1]
    assert current == rect
    assert current_size == size


def test_portrait_logical_size_maps_to_landscape_panel_size():
    assert native_size((320, 480), "portrait") == (480, 320)
    assert native_size((320, 480), "portrait_flipped") == (480, 320)


def test_flipped_partial_write_rotates_pixels_and_position():
    image = Image.new("RGB", (2, 1))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((1, 0), (0, 0, 255))
    native, pos = native_write(image, (10, 20), (480, 320), "landscape_flipped")
    assert pos == (468, 299)
    assert native.size == (2, 1)
    assert native.getpixel((0, 0)) == (0, 0, 255)
    assert native.getpixel((1, 0)) == (255, 0, 0)


def test_portrait_partial_write_becomes_a_landscape_crop():
    native, pos = native_write(
        Image.new("RGB", (20, 30)), (40, 50), (320, 480), "portrait"
    )
    assert native.size == (30, 20)
    assert pos == (50, 260)
