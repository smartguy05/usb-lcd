"""Rotating, filtered Windows notifications tile."""

from __future__ import annotations

from PIL import Image

from ..layout import TileContext
from ..notifications import NotificationSnapshot
from ..render import ERROR, MUTED, TEXT, WARNING, _fit, _font, _wrap
from .base import new_tile

ACCENT = "#4cc2ff"


def _empty(draw, size, title: str, detail: str, colour: str) -> None:
    width, height = size
    pad = max(6, round(min(width, height) * 0.07))
    heading, font = _fit(draw, title, width - 2 * pad, max(10, round(height * 0.14)), True)
    draw.text((width / 2, height * 0.39), heading, font=font, fill=colour, anchor="mm")
    body, body_font = _fit(draw, detail, width - 2 * pad, max(8, round(height * 0.09)))
    draw.text((width / 2, height * 0.62), body, font=body_font, fill=MUTED, anchor="mm")


def _selected(ctx: TileContext, snapshot: NotificationSnapshot):
    if not snapshot.items:
        return None, 0
    try:
        seconds = max(1.0, min(300.0, float(ctx.options.get("rotation_seconds", 8))))
    except (TypeError, ValueError):
        seconds = 8.0
    epoch = snapshot.changed_at or snapshot.updated_at or ctx.now
    elapsed = max(0.0, (ctx.now - epoch).total_seconds())
    index = int(elapsed / seconds) % len(snapshot.items)
    return snapshot.items[index], index


def render_notifications(ctx: TileContext) -> Image.Image:
    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options)
    snapshot = ctx.notifications or NotificationSnapshot()
    title = str(ctx.options.get("title") or "Notifications")

    states = {
        "unsupported": ("WINDOWS ONLY", MUTED),
        "permission_required": ("ENABLE ACCESS IN SETTINGS", WARNING),
        "denied": ("ACCESS DENIED", ERROR),
        "connecting": ("CONNECTING", ACCENT),
        "error": ("NOTIFICATIONS UNAVAILABLE", ERROR),
    }
    if snapshot.status in states:
        detail, colour = states[snapshot.status]
        _empty(draw, ctx.size, title, detail, colour)
        return image
    item, index = _selected(ctx, snapshot)
    if item is None:
        _empty(draw, ctx.size, title, "NO MATCHING NOTIFICATIONS", ACCENT)
        return image

    pad = max(6, round(min(width, height) * 0.055))
    inner = max(1, width - 2 * pad)
    small = max(8, round(height * 0.072))
    normal = max(9, round(height * 0.095))
    app, app_font = _fit(draw, f"{title} · {item.app_name}", inner * 0.7, small, True)
    draw.text((pad, pad), app, font=app_font, fill=ACCENT)
    position = f"{index + 1}/{len(snapshot.items)}"
    position, position_font = _fit(draw, position, inner * 0.25, small, True)
    draw.text((width - pad, pad), position, font=position_font, fill=MUTED, anchor="ra")
    heading, heading_font = _fit(draw, item.title, inner, normal, True)
    draw.text((pad, height * 0.27), heading, font=heading_font, fill=TEXT)

    body_font = _font(max(8, round(height * 0.085)))
    lines = _wrap(draw, item.body or "Notification", inner, body_font)
    max_lines = max(1, min(4, int((height * 0.40) / max(1, body_font.size * 1.25))))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1], body_font = _fit(draw, lines[-1] + "…", inner, body_font.size)
    line_height = max(10, round(body_font.size * 1.25))
    for line_index, line in enumerate(lines):
        draw.text((pad, height * 0.46 + line_index * line_height), line, font=body_font, fill=TEXT)

    seconds = max(0, int((ctx.now - item.created_at).total_seconds()))
    age = "now" if seconds < 60 else f"{seconds // 60}m ago" if seconds < 3600 else f"{seconds // 3600}h ago"
    age, age_font = _fit(draw, age, inner, small)
    draw.text((width - pad, height - pad), age, font=age_font, fill=MUTED, anchor="rd")
    return image
