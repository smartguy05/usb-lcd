import os

import pytest
from PIL import Image

from usb_lcd_dashboard import background as bg_module
from usb_lcd_dashboard.background import FIT_MODES, Background, background_layer


SIZE = (1920, 462)


@pytest.fixture(autouse=True)
def clear_cache():
    bg_module._CACHE.clear()
    bg_module._WARNED.clear()
    yield
    bg_module._CACHE.clear()
    bg_module._WARNED.clear()


@pytest.fixture
def wallpaper(tmp_path):
    """A deliberately wrong-shaped image, so fit modes have work to do."""
    path = tmp_path / "wall.png"
    image = Image.new("RGB", (800, 600), "#204060")
    image.save(path)
    return path


def test_a_plain_colour_fills_the_frame():
    frame = background_layer(Background(color="#081018"), SIZE)
    assert frame.size == SIZE
    assert frame.mode == "RGB"
    assert frame.getpixel((0, 0)) == (8, 16, 24)
    assert frame.getpixel((1919, 461)) == (8, 16, 24)


@pytest.mark.parametrize("fit", FIT_MODES)
def test_every_fit_mode_returns_exactly_the_requested_size(wallpaper, fit):
    frame = background_layer(Background(image=wallpaper, fit=fit), SIZE)
    assert frame.size == SIZE
    assert frame.mode == "RGB"


def test_cover_leaves_no_matting(wallpaper):
    """cover crops the overflow, so every pixel comes from the image."""
    frame = background_layer(
        Background(color="#ff0000", image=wallpaper, fit="cover"), SIZE
    )
    assert frame.getpixel((0, 0)) == (32, 64, 96)
    assert frame.getpixel((1919, 461)) == (32, 64, 96)


def test_contain_mats_the_edges_with_the_colour(wallpaper):
    frame = background_layer(
        Background(color="#ff0000", image=wallpaper, fit="contain"), SIZE
    )
    assert frame.getpixel((0, 0)) == (255, 0, 0)          # matted
    assert frame.getpixel((960, 231)) == (32, 64, 96)     # image, centred


def test_center_keeps_the_native_size_and_mats_around_it(wallpaper):
    frame = background_layer(
        Background(color="#ff0000", image=wallpaper, fit="center"), SIZE
    )
    assert frame.getpixel((0, 231)) == (255, 0, 0)
    assert frame.getpixel((960, 231)) == (32, 64, 96)


def test_a_missing_image_falls_back_to_the_colour_without_raising(tmp_path):
    absent = tmp_path / "nope.png"
    frame = background_layer(Background(color="#081018", image=absent), SIZE)
    assert frame.size == SIZE
    assert frame.getpixel((100, 100)) == (8, 16, 24)


def test_an_unreadable_image_falls_back_to_the_colour(tmp_path):
    junk = tmp_path / "broken.png"
    junk.write_bytes(b"this is not a png")
    frame = background_layer(Background(color="#081018", image=junk), SIZE)
    assert frame.getpixel((100, 100)) == (8, 16, 24)


def test_the_warning_is_only_logged_once_per_path(tmp_path, caplog):
    absent = tmp_path / "nope.png"
    with caplog.at_level("WARNING"):
        for _ in range(5):
            background_layer(Background(image=absent), SIZE)
    assert len([r for r in caplog.records if "Background image" in r.message]) == 1


def test_the_scaled_image_is_cached(wallpaper):
    background_layer(Background(image=wallpaper), SIZE)
    assert len(bg_module._CACHE) == 1
    key = next(iter(bg_module._CACHE))
    background_layer(Background(image=wallpaper), SIZE)
    assert list(bg_module._CACHE) == [key]


def test_a_changed_file_invalidates_the_cache(wallpaper):
    background_layer(Background(image=wallpaper), SIZE)
    first = next(iter(bg_module._CACHE))
    Image.new("RGB", (800, 600), "#00ff00").save(wallpaper)
    stat = wallpaper.stat()
    os.utime(wallpaper, (stat.st_atime, stat.st_mtime + 10))
    frame = background_layer(Background(image=wallpaper), SIZE)
    assert list(bg_module._CACHE) != [first]
    assert frame.getpixel((960, 231)) == (0, 255, 0)


def test_a_different_size_or_fit_is_not_served_from_the_cache(wallpaper):
    wide = background_layer(Background(image=wallpaper), (1920, 462))
    small = background_layer(Background(image=wallpaper), (480, 320))
    assert wide.size == (1920, 462)
    assert small.size == (480, 320)


def test_the_caller_gets_a_copy_it_can_paste_onto(wallpaper):
    first = background_layer(Background(image=wallpaper), SIZE)
    first.paste(Image.new("RGB", (100, 100), "#ffffff"), (0, 0))
    second = background_layer(Background(image=wallpaper), SIZE)
    assert second.getpixel((10, 10)) == (32, 64, 96)
