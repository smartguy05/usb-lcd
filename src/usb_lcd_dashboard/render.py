from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .model import SessionState


WIDTH, HEIGHT = 480, 320
BACKGROUND = "#081018"
PANEL = "#101c28"
TEXT = "#f2f7fb"
MUTED = "#8aa0b2"
CLAUDE = "#d97757"
CODEX = "#2bc48a"
WARNING = "#ffca3a"
ERROR = "#ff5f69"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    names = [
        str(windows_fonts / ("segoeuib.ttf" if bold else "segoeui.ttf")),
        "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit(draw: ImageDraw.ImageDraw, text: str, width: int, size: int, bold: bool = False):
    font = _font(size, bold)
    while text and draw.textlength(text, font=font) > width:
        text = text[:-2].rstrip() + "…"
    return text, font


def _duration(seconds: int) -> str:
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _branch(cwd: str) -> str:
    if not cwd or not Path(cwd).is_dir():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.15,
        )
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def render_dashboard(state: SessionState, now: datetime) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    accent = CLAUDE if state.provider == "claude" else CODEX
    if state.phase == "APPROVAL":
        accent = WARNING
    elif state.phase == "ERROR":
        accent = ERROR

    draw.rounded_rectangle((12, 10, 468, 62), radius=12, fill=PANEL)
    draw.rounded_rectangle((12, 10, 22, 62), radius=5, fill=accent)
    provider = state.provider.upper()
    draw.text((36, 20), provider, font=_font(25, True), fill=accent)
    model, model_font = _fit(draw, state.model or "model pending", 245, 18)
    draw.text((455 - draw.textlength(model, font=model_font), 25), model, font=model_font, fill=MUTED)

    phase = state.phase
    if state.phase == "TOOL" and state.detail:
        phase = f"TOOL · {state.detail}"
    elif state.phase == "APPROVAL":
        phase = "APPROVAL NEEDED"
    phase, phase_font = _fit(draw, phase, 430, 43, True)
    draw.text((24, 80), phase, font=phase_font, fill=accent)

    project = state.project
    branch = _branch(state.cwd)
    project_line = f"{project}  ·  {branch}" if branch else project
    project_line, project_font = _fit(draw, project_line, 430, 23, True)
    draw.text((24, 139), project_line, font=project_font, fill=TEXT)
    if state.detail and state.phase in {"APPROVAL", "ERROR"}:
        detail, detail_font = _fit(draw, state.detail, 430, 17)
        draw.text((24, 171), detail, font=detail_font, fill=MUTED)

    y = 209
    draw.text((24, y), "CONTEXT USED", font=_font(15, True), fill=MUTED)
    percent = state.context_percent
    percent_text = f"{percent:.0f}%" if percent is not None else "—"
    draw.text((424, y), percent_text, font=_font(16, True), fill=TEXT)
    draw.rounded_rectangle((24, y + 25, 456, y + 39), radius=7, fill="#1d3040")
    if percent is not None:
        filled = 24 + int(432 * max(0, min(percent, 100)) / 100)
        draw.rounded_rectangle((24, y + 25, max(31, filled), y + 39), radius=7, fill=accent)

    elapsed = int((now - state.started_at).total_seconds())
    left = f"ELAPSED  {_duration(elapsed)}"
    token_bits = []
    if state.input_tokens is not None:
        token_bits.append(f"IN {state.input_tokens / 1000:.1f}K")
    if state.output_tokens is not None:
        token_bits.append(f"OUT {state.output_tokens / 1000:.1f}K")
    if state.cost_usd is not None:
        token_bits.append(f"${state.cost_usd:.2f}")
    right = "  ".join(token_bits) or "LIVE SESSION"
    draw.text((24, 278), left, font=_font(15, True), fill=MUTED)
    right_font = _font(15, True)
    draw.text((456 - draw.textlength(right, font=right_font), 278), right, font=right_font, fill=MUTED)
    return image


def render_idle(title: str, now: datetime, connected: bool = True) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((22, 22, 458, 298), radius=22, fill=PANEL)
    draw.text((44, 51), title, font=_font(24, True), fill=MUTED)
    clock = now.astimezone().strftime("%-I:%M")
    clock_font = _font(98, True)
    draw.text(
        ((WIDTH - draw.textlength(clock, font=clock_font)) / 2, 93),
        clock,
        font=clock_font,
        fill=TEXT,
    )
    date = now.astimezone().strftime("%A · %B %-d")
    date_font = _font(22)
    draw.text(
        ((WIDTH - draw.textlength(date, font=date_font)) / 2, 218),
        date,
        font=date_font,
        fill=MUTED,
    )
    status = "LCD CONNECTED" if connected else "WAITING FOR LCD"
    color = CODEX if connected else WARNING
    status_font = _font(14, True)
    draw.text(
        ((WIDTH - draw.textlength(status, font=status_font)) / 2, 267),
        status,
        font=status_font,
        fill=color,
    )
    return image

