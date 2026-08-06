from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from .render import BACKGROUND

LOG = logging.getLogger(__name__)

FIT_MODES = ("cover", "contain", "stretch", "center")

# Decoding and rescaling a wallpaper on every frame at 2 Hz would cost more than
# everything else in the render path put together, so the scaled result is kept.
# mtime is part of the key, which means replacing the file on disk is picked up
# without restarting the daemon.
_CACHE: dict[tuple[str, float, tuple[int, int], str], Image.Image] = {}
_WARNED: set[str] = set()


@dataclass(frozen=True, slots=True)
class Background:
    color: str = BACKGROUND
    image: Path | None = None
    fit: str = "cover"


def _scaled(image: Image.Image, size: tuple[int, int], fit: str, color: str) -> Image.Image:
    if fit == "stretch":
        return image.resize(size)
    if fit == "cover":
        return ImageOps.fit(image, size)
    if fit == "contain":
        inner = ImageOps.contain(image, size)
    else:  # center: native size, no scaling
        inner = image
    canvas = Image.new("RGB", size, color)
    canvas.paste(
        inner,
        ((size[0] - inner.width) // 2, (size[1] - inner.height) // 2),
    )
    return canvas


def background_layer(bg: Background, size: tuple[int, int]) -> Image.Image:
    """The base layer a frame is composed onto: an RGB image of exactly `size`.

    A background image that will not load falls back to the solid colour and
    warns once rather than raising. A wallpaper is decoration; losing it must not
    cost the panel its dashboard, and a config synced between two machines can
    legitimately name a path that only exists on one of them.
    """
    if bg.image is None:
        return Image.new("RGB", size, bg.color)

    key_path = str(bg.image)
    try:
        mtime = bg.image.stat().st_mtime
    except OSError as exc:
        if key_path not in _WARNED:
            _WARNED.add(key_path)
            LOG.warning("Background image unavailable (%s); using %s", exc, bg.color)
        return Image.new("RGB", size, bg.color)

    key = (key_path, mtime, size, bg.fit)
    cached = _CACHE.get(key)
    if cached is None:
        try:
            with Image.open(bg.image) as handle:
                source = handle.convert("RGB")
        except (OSError, ValueError) as exc:
            if key_path not in _WARNED:
                _WARNED.add(key_path)
                LOG.warning("Background image unreadable (%s); using %s", exc, bg.color)
            return Image.new("RGB", size, bg.color)
        cached = _scaled(source, size, bg.fit, bg.color)
        _CACHE.clear()  # only ever one background in play; do not grow unbounded
        _CACHE[key] = cached
        _WARNED.discard(key_path)

    # A copy, because the caller composites tiles onto what it gets back.
    return cached.copy()
