"""Shared scaffolding for tile widgets."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageColor, ImageDraw

from ..render import MUTED, PANEL, TEXT, TRACK, _font

TRANSPARENT = ("transparent", "none", "")


def panel_fill(
    options: dict[str, Any], default_opacity: float = 1.0
) -> tuple[int, int, int, int] | None:
    """The tile's own backdrop, or None to let the background show through.

    A tile can be a solid card, translucent over a wallpaper, or nothing at all
    but its text.
    """
    raw = options.get("background", PANEL)
    if raw is None or (isinstance(raw, str) and raw.strip().lower() in TRANSPARENT):
        return None
    red, green, blue = ImageColor.getrgb(str(raw))[:3]
    try:
        opacity = float(options.get("opacity", default_opacity))
    except (TypeError, ValueError):
        opacity = 1.0
    alpha = round(max(0.0, min(1.0, opacity)) * 255)
    return (red, green, blue, alpha)


def new_tile(
    size: tuple[int, int], options: dict[str, Any], default_opacity: float = 1.0
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A transparent tile-sized canvas with the configured card drawn on it."""
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fill = panel_fill(options, default_opacity)
    if fill is not None:
        radius = max(4, round(min(width, height) * 0.05))
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=fill)
    return image, draw


def context_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    percent: float | None,
    accent: str,
    *,
    label_size: int = 0,
    gap: int | None = None,
) -> None:
    """The "CONTEXT USED" meter, caption and all, inside ``box``.

    ``label_size`` of 0 draws the track alone, which is what a tile too short for
    a caption wants — the bar still reads as a meter without it. ``gap`` is the
    drop from the caption to the track, for a caller that wants it tied to the
    tile's height rather than to the font.

    render.py draws this a third time with its own literal coordinates. That copy
    is deliberately left alone: test_legacy_identical.py pins the 3.5" panel's
    output pixel for pixel, and the two differ in caption sizing and in the
    minimum-fill floor, so folding it in here would grow this signature by three
    parameters to serve one caller that must not change at all.
    """
    left, top, right, bottom = box
    if label_size > 0:
        font = _font(label_size, True)
        draw.text((left, top), "CONTEXT USED", font=font, fill=MUTED)
        draw.text(
            (right, top),
            f"{percent:.0f}%" if percent is not None else "—",
            font=font,
            fill=TEXT,
            anchor="ra",
        )
        track_top = top + (round(label_size * 1.7) if gap is None else gap)
    else:
        track_top = top

    if bottom - track_top < 3:
        return
    radius = max(3, round((bottom - track_top) / 2))
    draw.rounded_rectangle((left, track_top, right, bottom), radius=radius, fill=TRACK)
    if percent is None:
        return
    span = right - left
    filled = left + round(span * max(0.0, min(percent, 100.0)) / 100)
    draw.rounded_rectangle(
        (left, track_top, max(left + radius * 2, filled), bottom),
        radius=radius,
        fill=accent,
    )
