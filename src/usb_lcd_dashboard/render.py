from __future__ import annotations

import functools
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import NO_WINDOW
from .model import SessionState


# The 3.5" Turing panel's own dimensions. Every coordinate in render_dashboard
# and render_idle is a literal derived from these two numbers, which is why they
# stay here rather than becoming a global claim about "the display": a second
# panel has its own size and gets it from the config.
LEGACY_WIDTH, LEGACY_HEIGHT = 480, 320
BACKGROUND = "#081018"
PANEL = "#101c28"
TEXT = "#f2f7fb"
MUTED = "#8aa0b2"
CLAUDE = "#d97757"
CODEX = "#2bc48a"
WARNING = "#ffca3a"
ERROR = "#ff5f69"
TRACK = "#1d3040"


@functools.lru_cache(maxsize=128)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Cached because a tiled frame asks for a lot of fonts.

    render_dashboard alone calls this ~10 times per frame; four tiles make it
    ~40, each one otherwise parsing a TrueType file again. Font objects are
    reusable across ImageDraw instances, so the cache changes no pixels.
    """
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


def _fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    size: int,
    bold: bool = False,
    min_size: int | None = None,
):
    font = _font(size, bold)
    while min_size and size > min_size and draw.textlength(text, font=font) > width:
        size -= 2
        font = _font(size, bold)
    while text and draw.textlength(text, font=font) > width:
        text = text[:-2].rstrip() + "…"
    return text, font


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, width: int, font: ImageFont.FreeTypeFont
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        while draw.textlength(word, font=font) > width:
            cut = 1
            while cut < len(word) and draw.textlength(word[: cut + 1], font=font) <= width:
                cut += 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def _fit_headline(draw: ImageDraw.ImageDraw, text: str, width: int, max_size: int = 43):
    """One big line where it fits, otherwise two smaller ones.

    Activity text ("Editing src/usb_lcd_dashboard/render.py") is far longer
    than the phase words this line used to hold, and truncating it throws away
    the part that identifies the work.

    The size ladder is tuned for the 3.5" panel's 430px headline. max_size
    scales it so a taller tile can start bigger and a cramped one smaller; the
    default reproduces the original ladder exactly.
    """
    scale = max_size / 43
    single = [max(8, round(size * scale)) for size in (43, 39, 35, 31)]
    double = [max(8, round(size * scale)) for size in (30, 28, 26, 24)]
    for size in single:
        font = _font(size, True)
        if draw.textlength(text, font=font) <= width:
            return [text], font
    for size in double:
        font = _font(size, True)
        lines = _wrap(draw, text, width, font)
        if len(lines) <= 2:
            return lines, font
    font = _font(double[-1], True)
    lines = _wrap(draw, text, width, font)[:2]
    lines[-1] = _fit(draw, lines[-1] + "…", width, double[-1], True)[0]
    return lines, font


def _duration(seconds: int) -> str:
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


_BRANCH_TTL = 15.0
_BRANCH_CACHE: dict[str, tuple[float, str]] = {}


def _branch(cwd: str) -> str:
    """The current git branch, cached for _BRANCH_TTL seconds.

    This spawns a process, and a tiled frame calls it once per agent tile: three
    tiles at 2 Hz is six git invocations a second, each with a 150ms timeout.
    A branch does not change that fast. Empty results are cached too, so a
    non-repo cwd stops paying for the lookup at all.
    """
    if not cwd or not Path(cwd).is_dir():
        return ""
    cached = _BRANCH_CACHE.get(cwd)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _BRANCH_TTL:
        return cached[1]
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.15,
            creationflags=NO_WINDOW,
        )
        branch = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        branch = ""
    _BRANCH_CACHE[cwd] = (now, branch)
    return branch


def render_dashboard(state: SessionState, now: datetime) -> Image.Image:
    image = Image.new("RGB", (LEGACY_WIDTH, LEGACY_HEIGHT), BACKGROUND)
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

    # Prefer the agent's own activity text ("Editing render.py") over the phase
    # word: it is the line the terminal shows, and it says far more than a tool
    # name. Phases that are not work in progress keep their own label.
    headline = state.phase
    if state.phase == "APPROVAL":
        headline = "APPROVAL NEEDED"
    elif state.activity and state.phase in {"TOOL", "THINKING", "ACTIVE"}:
        headline = state.activity
    lines, headline_font = _fit_headline(draw, headline, 430)
    headline_size = getattr(headline_font, "size", 43)
    line_height = int(headline_size * 1.2)
    top = 80 if len(lines) > 1 else 80 + (43 - headline_size) // 2
    for index, line in enumerate(lines):
        draw.text((24, top + index * line_height), line, font=headline_font, fill=accent)

    project_y = max(139, top + len(lines) * line_height + 6)
    project = state.project
    branch = _branch(state.cwd)
    project_line = f"{project}  ·  {branch}" if branch else project
    project_line, project_font = _fit(draw, project_line, 430, 23, True)
    draw.text((24, project_y), project_line, font=project_font, fill=TEXT)
    if state.detail and state.phase in {"APPROVAL", "ERROR"}:
        detail, detail_font = _fit(draw, state.detail, 430, 17)
        draw.text((24, project_y + 32), detail, font=detail_font, fill=MUTED)

    # Not widgets.base.context_bar: this card's output is pinned pixel for pixel
    # by test_legacy_identical.py, and its caption sizing and fill floor differ
    # from the tile version's. The duplication is deliberate.
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
    image = Image.new("RGB", (LEGACY_WIDTH, LEGACY_HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((22, 22, 458, 298), radius=22, fill=PANEL)
    draw.text((44, 51), title, font=_font(24, True), fill=MUTED)
    local = now.astimezone()
    clock = f"{local.hour % 12 or 12}:{local:%M}"
    clock_font = _font(98, True)
    draw.text(
        ((LEGACY_WIDTH - draw.textlength(clock, font=clock_font)) / 2, 93),
        clock,
        font=clock_font,
        fill=TEXT,
    )
    date = f"{local:%A · %B} {local.day}"
    date_font = _font(22)
    draw.text(
        ((LEGACY_WIDTH - draw.textlength(date, font=date_font)) / 2, 218),
        date,
        font=date_font,
        fill=MUTED,
    )
    status = "LCD CONNECTED" if connected else "WAITING FOR LCD"
    color = CODEX if connected else WARNING
    status_font = _font(14, True)
    draw.text(
        ((LEGACY_WIDTH - draw.textlength(status, font=status_font)) / 2, 267),
        status,
        font=status_font,
        fill=color,
    )
    return image

