"""The Claude Code / Codex session card, sized to whatever tile it is given.

Same information and same reading order as the 3.5" panel's card, but every
coordinate is a fraction of the tile rather than a literal. The ratios are taken
from the 480x320 original, so a tile of that shape looks like the card it came
from and a squarer one scales sensibly.
"""

from __future__ import annotations

from PIL import Image

from ..layout import TileContext
from ..render import (
    CLAUDE,
    CODEX,
    ERROR,
    MUTED,
    TEXT,
    WARNING,
    _branch,
    _duration,
    _fit,
    _fit_headline,
    _font,
)
from .base import context_bar, new_tile


def _accent(phase: str, provider: str) -> str:
    if phase == "APPROVAL":
        return WARNING
    if phase == "ERROR":
        return ERROR
    return CLAUDE if provider == "claude" else CODEX


def _headline(state) -> str:
    """Prefer the agent's own activity line over the phase word.

    "Editing render.py" is what the terminal shows and says far more than a tool
    name; phases that are not work in progress keep their own label.
    """
    if state.phase == "APPROVAL":
        return "APPROVAL NEEDED"
    if state.activity and state.phase in {"TOOL", "THINKING", "ACTIVE"}:
        return state.activity
    return state.phase


def _empty(ctx: TileContext) -> Image.Image:
    """A tile with no session. Deliberately quiet — several of these at once
    should not compete with the ones that have something to say."""
    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options, ctx.card_opacity)
    inner = max(1, width - 2 * max(6, round(width * 0.06)))
    slot = f"SLOT {ctx.slot + 1}" if ctx.slot >= 0 else "IDLE"
    label, label_font = _fit(draw, slot, inner, max(9, round(height * 0.055)), True)
    draw.text((width / 2, height * 0.44), label, font=label_font, fill=MUTED, anchor="mm")
    status = "NO ACTIVE SESSION" if ctx.connected else "WAITING FOR LCD"
    colour = MUTED if ctx.connected else WARNING
    text, font = _fit(draw, status, inner, max(8, round(height * 0.042)), True)
    draw.text((width / 2, height * 0.56), text, font=font, fill=colour, anchor="mm")
    return image


def render_agent(ctx: TileContext) -> Image.Image:
    state = ctx.session
    if state is None:
        return _empty(ctx)

    width, height = ctx.size
    image, draw = new_tile(ctx.size, ctx.options, ctx.card_opacity)
    accent = _accent(state.phase, state.provider)
    pad = max(8, round(width * 0.05))
    inner = max(1, width - 2 * pad)
    right = width - pad

    # Header: the accent spine and pill from the original card.
    bar_width = max(4, round(width * 0.021))
    header_top = round(height * 0.031)
    header_bottom = header_top + max(18, round(height * 0.1625))
    spine = max(3, round(height * 0.016))
    draw.rounded_rectangle(
        (pad, header_top, pad + bar_width, header_bottom), radius=spine, fill=accent
    )
    text_left = pad + bar_width + max(6, round(width * 0.03))
    provider, provider_font = _fit(
        draw,
        state.provider.upper(),
        max(1, inner // 2),
        max(10, round(height * 0.078)),
        True,
        min_size=10,
    )
    draw.text((text_left, header_top + spine), provider, font=provider_font, fill=accent)
    model, model_font = _fit(
        draw,
        state.model or "model pending",
        max(1, right - text_left - draw.textlength(provider, font=provider_font) - 12),
        max(9, round(height * 0.056)),
        min_size=9,
    )
    draw.text(
        (right, header_top + spine + round(height * 0.016)),
        model,
        font=model_font,
        fill=MUTED,
        anchor="ra",
    )

    # Headline: the activity line, as large as it will go.
    lines, headline_font = _fit_headline(
        draw, _headline(state), inner, max_size=max(12, round(height * 0.134))
    )
    headline_size = getattr(headline_font, "size", 12)
    line_height = round(headline_size * 1.2)
    top = round(height * 0.25)
    for index, line in enumerate(lines):
        draw.text((pad, top + index * line_height), line, font=headline_font, fill=accent)

    project_y = max(round(height * 0.434), top + len(lines) * line_height + 6)
    branch = _branch(state.cwd)
    project_line = f"{state.project}  ·  {branch}" if branch else state.project
    project_line, project_font = _fit(
        draw, project_line, inner, max(10, round(height * 0.072)), True, min_size=10
    )
    draw.text((pad, project_y), project_line, font=project_font, fill=TEXT)
    if state.detail and state.phase in {"APPROVAL", "ERROR"}:
        detail, detail_font = _fit(
            draw, state.detail, inner, max(9, round(height * 0.053)), min_size=9
        )
        draw.text(
            (pad, project_y + round(height * 0.1)), detail, font=detail_font, fill=MUTED
        )

    # Context bar.
    label_size = max(9, round(height * 0.047))
    bar_y = round(height * 0.653)
    gap = round(height * 0.078)
    context_bar(
        draw,
        (pad, bar_y, right, bar_y + gap + max(6, round(height * 0.044))),
        state.context_percent,
        accent,
        label_size=label_size,
        gap=gap,
    )

    # Footer.
    footer_y = round(height * 0.869)
    footer_font = _font(label_size, True)
    elapsed = int((ctx.now - state.started_at).total_seconds())
    draw.text((pad, footer_y), f"ELAPSED  {_duration(elapsed)}", font=footer_font, fill=MUTED)
    bits = []
    if state.input_tokens is not None:
        bits.append(f"IN {state.input_tokens / 1000:.1f}K")
    if state.output_tokens is not None:
        bits.append(f"OUT {state.output_tokens / 1000:.1f}K")
    if state.cost_usd is not None:
        bits.append(f"${state.cost_usd:.2f}")
    tail, tail_font = _fit(draw, "  ".join(bits) or "LIVE SESSION", inner, label_size, True)
    draw.text((right, footer_y), tail, font=tail_font, fill=MUTED, anchor="ra")
    return image
