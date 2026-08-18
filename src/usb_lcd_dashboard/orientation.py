"""Display mounting and lossless quarter-turn geometry."""

from __future__ import annotations

from collections.abc import Iterable

from PIL import Image

ORIENTATIONS = (
    "landscape",
    "portrait",
    "landscape_flipped",
    "portrait_flipped",
)

_TURNS = {name: index for index, name in enumerate(ORIENTATIONS)}


def turns(orientation: str) -> int:
    """Clockwise quarter turns made by the physical panel from landscape."""
    return _TURNS[orientation]


def native_size(size: tuple[int, int], orientation: str) -> tuple[int, int]:
    """The panel's unmounted landscape dimensions for a logical canvas."""
    return size[::-1] if turns(orientation) % 2 else size


def rotate_size(size: tuple[int, int], quarter_turns: int) -> tuple[int, int]:
    return size[::-1] if quarter_turns % 2 else size


def rotate_rect(
    rect: tuple[int, int, int, int],
    canvas: tuple[int, int],
    quarter_turns: int,
) -> tuple[int, int, int, int]:
    """Rotate an ``x, y, width, height`` rectangle clockwise in ``canvas``."""
    x, y, width, height = rect
    canvas_width, canvas_height = canvas
    for _ in range(quarter_turns % 4):
        x, y, width, height = canvas_height - y - height, x, height, width
        canvas_width, canvas_height = canvas_height, canvas_width
    return x, y, width, height


def rotate_layout(
    size: tuple[int, int],
    rects: Iterable[tuple[int, int, int, int]],
    source: str,
    target: str,
) -> tuple[tuple[int, int], list[tuple[int, int, int, int]]]:
    quarter_turns = (turns(target) - turns(source)) % 4
    return (
        rotate_size(size, quarter_turns),
        [rotate_rect(rect, size, quarter_turns) for rect in rects],
    )


def rotate_image_clockwise(image: Image.Image, quarter_turns: int) -> Image.Image:
    transpose = {
        0: None,
        1: Image.Transpose.ROTATE_270,
        2: Image.Transpose.ROTATE_180,
        3: Image.Transpose.ROTATE_90,
    }[quarter_turns % 4]
    return image if transpose is None else image.transpose(transpose)


def native_write(
    image: Image.Image,
    pos: tuple[int, int],
    canvas: tuple[int, int],
    orientation: str,
) -> tuple[Image.Image, tuple[int, int]]:
    """Map a logical full frame or crop into the landscape panel buffer."""
    # The panel is physically turned clockwise, so logical pixels are turned the
    # opposite way before transmission to remain upright to the viewer.
    quarter_turns = (-turns(orientation)) % 4
    rect = (pos[0], pos[1], image.width, image.height)
    x, y, _, _ = rotate_rect(rect, canvas, quarter_turns)
    return rotate_image_clockwise(image, quarter_turns), (x, y)
