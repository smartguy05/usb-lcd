"""A clock tile.

Every size is a fraction of the tile rather than a literal, so the same widget
works in a 404x438 column on the ultra-wide and in a squat strip.
"""

from __future__ import annotations

from PIL import Image

from ..layout import TileContext
from ..render import MUTED, TEXT, _fit, _font
from .base import new_tile


def render_clock(ctx: TileContext) -> Image.Image:
    width, height = ctx.size
    options = ctx.options
    image, draw = new_tile(ctx.size, options, ctx.card_opacity)
    pad = max(6, round(min(width, height) * 0.06))
    inner = max(1, width - 2 * pad)

    local = ctx.now.astimezone()
    hour12 = bool(options.get("hour12", True))
    # The leading zero is dropped on a 12-hour clock, as the idle screen does.
    clock = f"{local.hour % 12 or 12}:{local:%M}" if hour12 else f"{local:%H:%M}"

    title = str(options.get("title") or "")
    if title:
        label, label_font = _fit(draw, title, inner, max(9, round(height * 0.075)), True)
        draw.text((pad, pad), label, font=label_font, fill=MUTED)

    centre_y = round(height * (0.46 if title else 0.42))
    biggest = max(12, round(height * 0.42))

    if options.get("seconds"):
        seconds = f"{local:%S}"
        gap = max(3, round(width * 0.015))
        # The pair has to fit, not just the time: sizing the clock alone to the
        # tile pushes the seconds off the edge.
        size = biggest
        while True:
            clock_font = _font(size, True)
            seconds_font = _font(max(8, round(size * 0.28)), True)
            clock_width = draw.textlength(clock, font=clock_font)
            seconds_width = draw.textlength(seconds, font=seconds_font)
            if size <= 12 or clock_width + gap + seconds_width <= inner:
                break
            size -= 2
        left = (width - (clock_width + gap + seconds_width)) / 2
        draw.text((left, centre_y), clock, font=clock_font, fill=TEXT, anchor="lm")
        draw.text(
            (left + clock_width + gap, centre_y + round(size * 0.26)),
            seconds,
            font=seconds_font,
            fill=MUTED,
            anchor="lm",
        )
    else:
        clock_text, clock_font = _fit(draw, clock, inner, biggest, True, min_size=12)
        draw.text(
            (width / 2, centre_y), clock_text, font=clock_font, fill=TEXT, anchor="mm"
        )

    if options.get("show_date", True):
        date = f"{local:%A · %B} {local.day}"
        date_text, date_font = _fit(
            draw, date, inner, max(9, round(height * 0.075)), min_size=9
        )
        draw.text(
            (width / 2, round(height * 0.78)),
            date_text,
            font=date_font,
            fill=MUTED,
            anchor="mm",
        )
    return image
