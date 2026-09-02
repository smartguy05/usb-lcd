"""The active-background layer: an animated wallpaper drawn behind the tiles.

Covers: active_background.py

A red fox runs across the panel, exits one edge, dwells off-screen, then
re-enters from the other side. Its speed follows live CPU usage, which is why
this cannot be a stateless tile widget: a tile is a pure function of ``ctx.now``
(see widgets/crab.py), but a position that is the integral of a time-varying
speed has to be carried between frames. So this layer is deliberately stateful
and stepped once per frame by the daemon, and it composites *under* the
foreground tiles (see layout.compose's ``active_background`` overlay).

The fox art is a run-cycle of transparent PNGs under ``assets/fox`` (baked by
``tools/make_fox_sprites.py``; drop in your own equal-height frames to replace
it). Missing art or a missing psutil degrade rather than crash: no frames means
the layer simply draws nothing, and no psutil means a neutral mid speed.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from .config import ActiveBackgroundConfig

LOG = logging.getLogger(__name__)

FOX_DIR = Path(__file__).resolve().parent / "assets" / "fox"

# How long the fox stays off-screen between runs. A short beat so the panel is
# not busy with a fox at every moment, kept out of the config to hold its
# surface small.
DWELL_SECONDS = 2.5

# One full 6-frame leg cycle per this fraction of the fox's own width of travel,
# so the gait reads as running rather than sliding, at any speed.
STRIDE_FRACTION = 0.55

# psutil is an optional convenience. Without it the fox runs at a neutral speed
# rather than taking the panel down — the same bargain the tray and editor make.
try:  # pragma: no cover - import guard
    import psutil as _psutil
except Exception:  # pragma: no cover
    _psutil = None

_warned_no_frames = False


def _load_raw_frames() -> list[Image.Image]:
    """The run-cycle frames as RGBA, in filename order; [] if none/unreadable."""
    global _warned_no_frames
    frames: list[Image.Image] = []
    try:
        paths = sorted(FOX_DIR.glob("run_*.png"))
        for path in paths:
            with Image.open(path) as handle:
                frames.append(handle.convert("RGBA"))
    except OSError as exc:  # pragma: no cover - unreadable art is not fatal
        LOG.warning("Fox sprites unreadable (%s); active background disabled", exc)
        return []
    if not frames and not _warned_no_frames:
        _warned_no_frames = True
        LOG.warning("No fox sprites in %s; active background draws nothing", FOX_DIR)
    return frames


def _cpu_fraction() -> float:
    """Live CPU load in 0..1. Neutral 0.5 when psutil is unavailable.

    ``cpu_percent(interval=None)`` is non-blocking and reports usage since the
    previous call, which is exactly the once-per-frame cadence here.
    """
    if _psutil is None:
        return 0.5
    try:
        return max(0.0, min(1.0, _psutil.cpu_percent(interval=None) / 100.0))
    except Exception:  # pragma: no cover - never let a sampler fault the panel
        return 0.5


class ActiveBackground:
    """Stateful fox runner. ``step`` returns this frame's overlay, or None."""

    def __init__(self, cfg: ActiveBackgroundConfig) -> None:
        self.cfg = cfg
        self._raw = _load_raw_frames()
        # Frames scaled for the current panel size, rebuilt when size/scale change.
        self._scaled: list[Image.Image] = []
        self._scaled_key: tuple[int, int, float] | None = None
        self._fox_size = (0, 0)
        # Position of the fox's left edge, in panel pixels. None until the first
        # step knows the panel size and can start it just off the left edge.
        self._x: float | None = None
        self._phase = 0.0  # advances with distance; indexes the run cycle
        self._dwell = 0.0
        self.direction = 1  # +1 = rightward; the art faces right

    def reconfigure(self, cfg: ActiveBackgroundConfig) -> None:
        """Adopt edited settings without resetting the fox's position."""
        if cfg.scale != self.cfg.scale:
            self._scaled_key = None  # force a rescale on the next step
        self.cfg = cfg

    def _ensure_scaled(self, size: tuple[int, int]) -> None:
        key = (size[0], size[1], self.cfg.scale)
        if key == self._scaled_key:
            return
        self._scaled_key = key
        if not self._raw:
            self._scaled = []
            self._fox_size = (0, 0)
            return
        target_h = max(1, round(self.cfg.scale * size[1]))
        aspect = self._raw[0].width / self._raw[0].height
        target_w = max(1, round(target_h * aspect))
        scaled = [f.resize((target_w, target_h), Image.LANCZOS) for f in self._raw]
        if self.direction < 0:
            scaled = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in scaled]
        self._scaled = scaled
        self._fox_size = (target_w, target_h)
        # Keep the fox on the (possibly resized) panel.
        if self._x is not None:
            self._x = max(-target_w, min(float(size[0]), self._x))

    def step(self, dt: float, size: tuple[int, int]) -> Image.Image | None:
        """Advance the fox by ``dt`` seconds and return the overlay for ``size``.

        Returns None while the fox is off-screen (its dwell), so no fox pixels
        are contributed to the frame.
        """
        self._ensure_scaled(size)
        if not self._scaled:
            return None
        width, height = size
        fox_w, fox_h = self._fox_size

        if self._x is None:
            # Enter from just off the leading edge.
            self._x = -float(fox_w) if self.direction > 0 else float(width)

        if self._dwell > 0.0:
            self._dwell = max(0.0, self._dwell - dt)
            return None

        cpu = _cpu_fraction()
        speed = self.cfg.speed_min + (self.cfg.speed_max - self.cfg.speed_min) * cpu
        travel = speed * max(0.0, dt)
        self._x += self.direction * travel
        stride = max(1.0, fox_w * STRIDE_FRACTION)
        self._phase = (self._phase + travel / stride) % len(self._scaled)

        # Fully exited the far edge? Dwell, then re-enter from the other side
        # (same direction), so it "reappears from the other side".
        if self.direction > 0 and self._x >= width:
            self._x = -float(fox_w)
            self._dwell = DWELL_SECONDS
            return None
        if self.direction < 0 and self._x <= -fox_w:
            self._x = float(width)
            self._dwell = DWELL_SECONDS
            return None

        frame = self._scaled[int(self._phase) % len(self._scaled)]
        if self.cfg.opacity < 1.0:
            alpha = frame.getchannel("A").point(
                lambda a: round(a * self.cfg.opacity)
            )
            frame = frame.copy()
            frame.putalpha(alpha)

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        y = height - fox_h  # feet along the panel's bottom edge
        overlay.paste(frame, (round(self._x), y), frame)
        return overlay
