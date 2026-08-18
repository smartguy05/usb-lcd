"""Responsive Claude subscription usage widget."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from ..claude_limits import ClaudeLimitsSnapshot, LimitWindow
from ..layout import TileContext
from ..render import CLAUDE, ERROR, MUTED, TEXT, WARNING, _fit
from .base import new_tile

TRACK = "#283442"
GOOD = "#75e0b4"


def _colour(percent: float) -> str:
    if percent >= 90:
        return ERROR
    if percent >= 75:
        return WARNING
    return CLAUDE


def _countdown(reset: datetime, now: datetime) -> str:
    current = now if now.tzinfo else now.astimezone()
    seconds = max(0, int((reset - current.astimezone(reset.tzinfo)).total_seconds()))
    if seconds < 60:
        return "resets in <1m"
    minutes = seconds // 60
    if minutes < 60:
        return f"resets in {minutes}m"
    hours = minutes // 60
    minutes %= 60
    if hours < 24:
        return f"resets in {hours}h {minutes}m"
    days = hours // 24
    hours %= 24
    return f"resets in {days}d {hours}h"


def _active(window: LimitWindow | None, now: datetime) -> bool:
    if window is None:
        return False
    current = now if now.tzinfo else now.astimezone()
    return window.resets_at > current.astimezone(window.resets_at.tzinfo)


def _bar(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], percent: float, colour: str) -> None:
    left, top, right, bottom = box
    radius = max(1, (bottom - top) // 2)
    draw.rounded_rectangle(box, radius=radius, fill=TRACK)
    fill_right = left + round((right - left) * percent / 100)
    if fill_right > left:
        draw.rounded_rectangle((left, top, max(left + radius * 2, fill_right), bottom), radius=radius, fill=colour)


def _row(draw: ImageDraw.ImageDraw, width: int, y: int, row_h: int, pad: int,
         label: str, window: LimitWindow, now: datetime) -> None:
    label_font_size = max(8, round(row_h * 0.24))
    label_text, label_font = _fit(draw, label, width * 0.55, label_font_size, True)
    pct_text, pct_font = _fit(draw, f"{window.used_percentage:.0f}%", width * 0.25, label_font_size, True)
    draw.text((pad, y), label_text, font=label_font, fill=TEXT)
    draw.text((width - pad, y), pct_text, font=pct_font, fill=TEXT, anchor="ra")
    bar_top = y + label_font.size + max(2, row_h // 16)
    bar_h = max(4, round(row_h * 0.14))
    _bar(draw, (pad, bar_top, width - pad, bar_top + bar_h), window.used_percentage, _colour(window.used_percentage))
    reset, reset_font = _fit(draw, _countdown(window.resets_at, now), width - pad * 2,
                             max(7, round(row_h * 0.19)))
    draw.text((width / 2, bar_top + bar_h + 2), reset, font=reset_font, fill=MUTED, anchor="ma")


def _ring(draw: ImageDraw.ImageDraw, width: int, top: int, available_h: int,
          window: LimitWindow, now: datetime) -> int:
    diameter = min(round(width * 0.48), round(available_h * 0.72))
    diameter = max(42, diameter)
    left = (width - diameter) // 2
    box = (left, top, left + diameter, top + diameter)
    stroke = max(5, diameter // 12)
    draw.arc(box, 135, 405, fill=TRACK, width=stroke)
    draw.arc(box, 135, 135 + 270 * window.used_percentage / 100,
             fill=_colour(window.used_percentage), width=stroke)
    pct, pct_font = _fit(draw, f"{window.used_percentage:.0f}%", diameter * 0.62,
                         max(16, round(diameter * 0.22)), True)
    draw.text((width / 2, top + diameter * 0.48), pct, font=pct_font, fill=GOOD, anchor="mm")
    label, label_font = _fit(draw, "5-hour session", diameter * 0.68,
                             max(8, round(diameter * 0.085)), True)
    draw.text((width / 2, top + diameter * 0.65), label, font=label_font, fill=TEXT, anchor="mm")
    reset, reset_font = _fit(draw, _countdown(window.resets_at, now), diameter * 0.9,
                             max(7, round(diameter * 0.075)))
    draw.text((width / 2, top + diameter + 3), reset, font=reset_font, fill=MUTED, anchor="ma")
    return top + diameter + reset_font.size + 6


def render_claude_limits(ctx: TileContext) -> Image.Image:
    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options, ctx.card_opacity)
    snapshot = ctx.claude_limits or ClaudeLimitsSnapshot()
    pad = max(5, round(min(width, height) * 0.045))
    title = str(ctx.options.get("title") or "Claude")
    title_text, title_font = _fit(draw, title, width - pad * 2,
                                  max(10, round(height * 0.075)), True)
    draw.text(
        (width / 2, pad),
        title_text,
        font=title_font,
        fill=CLAUDE,
        anchor="mt",
    )
    top = pad + title_font.size + max(5, round(height * 0.025))

    windows = [
        ("5-hour session", snapshot.five_hour),
        ("Weekly", snapshot.seven_day),
        ("Weekly · Fable", snapshot.fable),
    ]
    active = [(label, window) for label, window in windows if _active(window, ctx.now)]
    if not active:
        waiting, font = _fit(draw, "WAITING FOR CLAUDE USAGE", width - pad * 2,
                             max(9, round(height * 0.09)), True)
        draw.text((width / 2, height * 0.52), waiting, font=font, fill=MUTED, anchor="mm")
        return image

    roomy = height >= 260 and width / max(1, height) <= 1.55 and active[0][0] == "5-hour session"
    if roomy:
        first = active.pop(0)[1]
        assert first is not None
        top = _ring(
            draw,
            width,
            top,
            max(80, round(height * 0.58)),
            first,
            ctx.now,
        )

    remaining_h = max(1, height - top - pad)
    row_h = max(28, remaining_h // max(1, len(active))) if active else 0
    for index, (label, window) in enumerate(active):
        assert window is not None
        _row(draw, width, top + index * row_h, row_h, pad, label, window, ctx.now)

    all_windows = [window for _, window in windows if window is not None]
    if all_windows:
        newest = max(window.updated_at for window in all_windows)
        age = max(0, int((ctx.now.astimezone(newest.tzinfo) - newest).total_seconds()))
        if age >= 30 * 60:
            label = f"updated {age // 60}m ago" if age < 3600 else f"updated {age // 3600}h ago"
            footer, footer_font = _fit(
                draw, label, width * 0.3, max(6, round(height * 0.035))
            )
            draw.text(
                (width - pad, pad),
                footer,
                font=footer_font,
                fill=MUTED,
                anchor="ra",
            )
    return image
