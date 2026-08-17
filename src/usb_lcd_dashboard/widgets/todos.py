"""Human todo list tile."""

from __future__ import annotations

import math
from datetime import date

from PIL import Image

from ..layout import TileContext
from ..render import ERROR, MUTED, TEXT, WARNING, _fit
from ..todos import TodoItem, TodoSnapshot
from .base import new_tile

ACCENT = "#2bc48a"


def _deadline(item: TodoItem, today: date) -> tuple[str, str]:
    if not item.due_date:
        return "", MUTED
    due = date.fromisoformat(item.due_date)
    days = (due - today).days
    if days < 0:
        return "OVERDUE", ERROR
    if days == 0:
        return "TODAY", WARNING
    if days == 1:
        return "TOMORROW", WARNING
    return f"{due.strftime('%b')} {due.day}", MUTED


def render_todos(ctx: TileContext) -> Image.Image:
    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options)
    snapshot = ctx.todos or TodoSnapshot()
    title = str(ctx.options.get("title") or "Todos")
    pad = max(5, round(min(width, height) * 0.05))
    inner = max(1, width - pad * 2)
    heading_size = max(9, round(height * 0.075))
    heading, heading_font = _fit(draw, title, inner * 0.7, heading_size, True)
    draw.text((pad, pad), heading, font=heading_font, fill=ACCENT)

    count = len(snapshot.items)
    count_text, count_font = _fit(draw, f"{count} open", inner * 0.3, heading_size, True)
    draw.text((width - pad, pad), count_text, font=count_font, fill=MUTED, anchor="ra")
    if not snapshot.items:
        body, body_font = _fit(draw, "ALL CLEAR", inner, max(10, round(height * 0.12)), True)
        draw.text((width / 2, height * 0.55), body, font=body_font, fill=ACCENT, anchor="mm")
        return image

    top = max(pad + heading_font.size + 7, round(height * 0.20))
    footer_h = max(14, round(height * 0.10))
    row_h = max(20, round(height * 0.145))
    per_page = max(1, int((height - top - footer_h - pad) / row_h))
    pages = max(1, math.ceil(count / per_page))
    try:
        interval = max(1.0, float(ctx.options.get("rotation_seconds", 8)))
    except (TypeError, ValueError):
        interval = 8.0
    page = int(ctx.now.timestamp() // interval) % pages
    items = snapshot.items[page * per_page : (page + 1) * per_page]
    today = ctx.now.astimezone().date() if ctx.now.tzinfo else ctx.now.date()

    priority_colour = {"urgent": ERROR, "high": WARNING, "normal": ACCENT, "low": MUTED}
    for index, item in enumerate(items):
        y = top + index * row_h
        box = max(8, min(14, round(row_h * 0.42)))
        draw.rounded_rectangle((pad, y + 2, pad + box, y + 2 + box), radius=2, outline=priority_colour[item.priority])
        due, due_colour = _deadline(item, today)
        due_width = min(inner * 0.34, max(0, len(due) * heading_size * 0.68)) if due else 0
        available = max(1, inner - box - 8 - due_width)
        label, font = _fit(draw, item.title, available, max(8, round(row_h * 0.46)), item.priority in ("urgent", "high"))
        draw.text((pad + box + 7, y), label, font=font, fill=TEXT)
        if due:
            due_text, due_font = _fit(draw, due, max(1, due_width), max(7, round(row_h * 0.35)), True)
            draw.text((width - pad, y + 1), due_text, font=due_font, fill=due_colour, anchor="ra")

    footer = f"{page + 1}/{pages}" if pages > 1 else "prioritized"
    footer, footer_font = _fit(draw, footer, inner, max(7, round(height * 0.055)))
    draw.text((width - pad, height - pad), footer, font=footer_font, fill=MUTED, anchor="rd")
    return image
