"""A deterministic, low-write moving clock screen saver."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from .render import TEXT, _font


def render_screensaver(size: tuple[int, int], now: datetime) -> Image.Image:
    """Render a clock whose position changes once per minute on pure black."""
    width, height = size
    image = Image.new("RGB", size, "#000000")
    draw = ImageDraw.Draw(image)
    font_size = max(16, round(min(width, height) * 0.18))
    font = _font(font_size, True)
    value = now.astimezone().strftime("%H:%M")
    box = draw.textbbox((0, 0), value, font=font)
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    margin = max(8, round(min(width, height) * 0.05))
    span_x = max(0, width - text_width - margin * 2)
    span_y = max(0, height - text_height - margin * 2)
    minute = int(now.timestamp() // 60)
    # Co-prime multipliers walk the available area without mutable renderer
    # state; tests can reproduce any frame by naming its timestamp.
    x = margin + ((minute * 37) % (span_x + 1) if span_x else 0)
    y = margin + ((minute * 53) % (span_y + 1) if span_y else 0)
    draw.text((x, y), value, font=font, fill=TEXT)
    return image
