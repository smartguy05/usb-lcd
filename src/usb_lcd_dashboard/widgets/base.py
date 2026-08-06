"""Shared scaffolding for tile widgets."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageColor, ImageDraw

from ..render import PANEL

TRANSPARENT = ("transparent", "none", "")


def panel_fill(options: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """The tile's own backdrop, or None to let the background show through.

    A tile can be a solid card, translucent over a wallpaper, or nothing at all
    but its text.
    """
    raw = options.get("background", PANEL)
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in TRANSPARENT):
        return None
    red, green, blue = ImageColor.getrgb(str(raw))[:3]
    try:
        opacity = float(options.get("opacity", 1.0))
    except (TypeError, ValueError):
        opacity = 1.0
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    return (red, green, blue, alpha)


def new_tile(
    size: tuple[int, int], options: dict[str, Any]
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A transparent tile-sized canvas with the configured card drawn on it."""
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fill = panel_fill(options)
    if fill is not None:
        radius = max(4, round(min(width, height) * 0.05))
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=fill)
    return image, draw
