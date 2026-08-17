"""Latest-unread messaging tile."""

from __future__ import annotations

from PIL import Image

from ..layout import TileContext
from ..messaging import MessageSnapshot
from ..render import ERROR, MUTED, TEXT, WARNING, _fit, _font, _wrap
from .base import new_tile

DISCORD = "#5865f2"


def _age(ctx: TileContext, snapshot: MessageSnapshot) -> str:
    if snapshot.latest is None:
        return ""
    seconds = max(0, int((ctx.now - snapshot.latest.created_at).total_seconds()))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _empty(draw, size, title: str, detail: str, colour: str) -> None:
    width, height = size
    pad = max(6, round(min(width, height) * 0.07))
    inner = max(1, width - 2 * pad)
    heading, heading_font = _fit(draw, title, inner, max(10, round(height * 0.14)), True)
    draw.text((width / 2, height * 0.39), heading, font=heading_font, fill=colour, anchor="mm")
    body, body_font = _fit(draw, detail, inner, max(8, round(height * 0.095)))
    draw.text((width / 2, height * 0.62), body, font=body_font, fill=MUTED, anchor="mm")


def render_messages(ctx: TileContext) -> Image.Image:
    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options)
    snapshot = ctx.messages or MessageSnapshot()
    title = str(ctx.options.get("title") or "Discord")

    if snapshot.status == "unconfigured":
        _empty(draw, ctx.size, title, "SET UP DISCORD INTEGRATION", WARNING)
        return image
    if snapshot.status == "connecting":
        _empty(draw, ctx.size, title, "CONNECTING", DISCORD)
        return image
    if snapshot.status == "disconnected":
        _empty(draw, ctx.size, title, "CONNECT IN SETTINGS", MUTED)
        return image
    if snapshot.latest is None:
        if snapshot.status == "error":
            _empty(draw, ctx.size, title, "DISCORD UNAVAILABLE", ERROR)
        else:
            _empty(draw, ctx.size, title, "NO NEW MESSAGES", DISCORD)
        return image

    item = snapshot.latest
    pad = max(6, round(min(width, height) * 0.055))
    inner = max(1, width - 2 * pad)
    small = max(8, round(height * 0.075))
    normal = max(9, round(height * 0.095))

    heading, heading_font = _fit(draw, title, inner * 0.65, small, True)
    draw.text((pad, pad), heading, font=heading_font, fill=DISCORD)
    count = "99+ new" if snapshot.unread_conversations >= 100 else f"{snapshot.unread_conversations} new"
    count, count_font = _fit(draw, count, inner * 0.4, small, True)
    draw.text((width - pad, pad), count, font=count_font, fill=WARNING, anchor="ra")

    conversation, conversation_font = _fit(draw, item.conversation, inner, normal, True)
    draw.text((pad, height * 0.25), conversation, font=conversation_font, fill=TEXT)
    sender, sender_font = _fit(draw, item.sender, inner, small, True)
    draw.text((pad, height * 0.40), sender, font=sender_font, fill=DISCORD)

    preview_font = _font(max(8, round(height * 0.085)))
    lines = _wrap(draw, item.preview, inner, preview_font)
    max_lines = max(1, min(3, int((height * 0.35) / max(1, preview_font.size * 1.25))))
    lines = lines[:max_lines]
    if len(_wrap(draw, item.preview, inner, preview_font)) > max_lines and lines:
        lines[-1], preview_font = _fit(draw, lines[-1] + "…", inner, preview_font.size)
    line_height = max(10, round(preview_font.size * 1.25))
    for index, line in enumerate(lines):
        draw.text((pad, height * 0.54 + index * line_height), line, font=preview_font, fill=TEXT)

    footer = _age(ctx, snapshot)
    if snapshot.stale:
        footer = f"{footer} · STALE" if footer else "STALE"
    footer, footer_font = _fit(draw, footer, inner, small)
    draw.text((width - pad, height - pad), footer, font=footer_font, fill=MUTED, anchor="rd")
    return image
