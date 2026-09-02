#!/usr/bin/env python3
"""Bake a red-fox run-cycle sprite sheet to PNG frames.

The active-background layer (``active_background.py``) needs a small run-cycle of
transparent frames. Rather than commit opaque binary art with no provenance, the
frames are generated here from plain shapes so the result is reproducible and
reviewable, and anyone can re-run this to tweak the fox. If you would rather ship
real art, drop your own equal-height RGBA ``run_XX.png`` files into the same
directory — the loader is agnostic to how they were made.

The fox faces RIGHT; the runtime flips it horizontally for the return trip.

ImageDraw does not anti-alias, so every frame is drawn at SS× scale and reduced,
the same trick the crab widget uses (see widgets/crab.py).

Run:  python tools/make_fox_sprites.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

# Canonical 1x frame size. The runtime scales to a fraction of panel height, so
# this only fixes the sprite's aspect ratio and internal proportions.
W, H = 200, 120
SS = 4  # supersample factor
FRAMES = 6

OUT = Path(__file__).resolve().parent.parent / "src/usb_lcd_dashboard/assets/fox"

# Palette — a red fox: rust body, cream underside, near-black legs and ear tips.
RUST = (196, 92, 34, 255)
RUST_DARK = (150, 64, 20, 255)
CREAM = (244, 232, 210, 255)
BLACK = (34, 26, 22, 255)
NOSE = (26, 20, 18, 255)
EYE = (30, 22, 18, 255)
WHITE_TIP = (238, 230, 214, 255)


def _p(points):
    """Scale a list of 1x (x, y) points to supersample space."""
    return [(x * SS, y * SS) for x, y in points]


def _ell(draw, x0, y0, x1, y1, fill):
    """A 1x-coordinate ellipse, scaled into supersample space."""
    draw.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill)


def _dot(draw, cx, cy, r, fill):
    _ell(draw, cx - r, cy - r, cx + r, cy + r, fill)


def _line(draw, a, b, width, fill):
    draw.line([a[0] * SS, a[1] * SS, b[0] * SS, b[1] * SS], fill=fill, width=width * SS)
    # Rounded joints/caps: ImageDraw square-caps thick lines otherwise.
    for x, y in (a, b):
        _dot(draw, x, y, width / 2, fill)


def _leg(draw, hip, phase, front):
    """A two-segment leg swinging through a gallop phase (radians).

    Reach forward and fold back over the cycle; the paw traces a shallow arc so
    the gait reads as a run rather than a slide.
    """
    upper = 26 if front else 28
    lower = 22 if front else 24
    swing = math.sin(phase)
    lift = max(0.0, math.cos(phase))  # foot lifts on the recovery half
    thigh_ang = math.radians(90 + swing * 34)
    knee = (
        hip[0] + upper * math.cos(thigh_ang),
        hip[1] + upper * math.sin(thigh_ang) - lift * 6,
    )
    shin_ang = thigh_ang + math.radians(28 - swing * 26)
    paw = (
        knee[0] + lower * math.cos(shin_ang),
        knee[1] + lower * math.sin(shin_ang) - lift * 4,
    )
    _line(draw, hip, knee, 9, RUST_DARK)
    _line(draw, knee, paw, 7, BLACK)
    # Paw
    _ell(draw, paw[0] - 5, paw[1] - 4, paw[0] + 5, paw[1] + 4, BLACK)


def _draw_fox(frame_index: int) -> Image.Image:
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    t = frame_index / FRAMES
    cycle = t * 2 * math.pi
    bob = math.sin(cycle * 2) * 3  # body rises/falls twice per stride

    # Diagonal-pair gait: front-left with back-right, offset half a cycle.
    back_hip = (78, 74 + bob)
    front_hip = (140, 74 + bob)

    # Far legs first (drawn darker/behind), then body, then near legs.
    _leg(d, back_hip, cycle + math.pi + 0.5, front=False)
    _leg(d, front_hip, cycle + 0.5, front=True)

    # Tail: a bushy sweep off the rear haunch, cream tip.
    tail = _p([
        (74, 66 + bob), (52, 58 + bob), (30, 66 + bob), (18, 84 + bob),
        (26, 92 + bob), (40, 82 + bob), (58, 76 + bob), (74, 74 + bob),
    ])
    d.polygon(tail, fill=RUST)
    d.polygon(_p([(18, 84 + bob), (26, 92 + bob), (34, 84 + bob), (26, 76 + bob)]), fill=WHITE_TIP)

    # Body: haunch (rear) into a slimmer shoulder (front).
    _ell(d, 58, 48 + bob, 108, 88 + bob, RUST)
    _ell(d, 100, 52 + bob, 150, 84 + bob, RUST)
    # Cream underside.
    _ell(d, 74, 70 + bob, 140, 90 + bob, CREAM)

    # Neck + head.
    d.polygon(_p([
        (134, 58 + bob), (150, 44 + bob), (168, 40 + bob), (176, 52 + bob),
        (170, 62 + bob), (150, 70 + bob),
    ]), fill=RUST)
    # Snout
    d.polygon(_p([
        (168, 48 + bob), (192, 52 + bob), (192, 60 + bob), (168, 62 + bob),
    ]), fill=CREAM)
    d.polygon(_p([(168, 44 + bob), (190, 51 + bob), (168, 54 + bob)]), fill=RUST)
    # Nose
    _ell(d, 188, 53 + bob, 196, 60 + bob, NOSE)

    # Ears: pointed, black tips.
    d.polygon(_p([(150, 46 + bob), (156, 24 + bob), (166, 44 + bob)]), fill=RUST)
    d.polygon(_p([(153, 34 + bob), (156, 24 + bob), (161, 37 + bob)]), fill=BLACK)
    d.polygon(_p([(160, 44 + bob), (170, 26 + bob), (176, 46 + bob)]), fill=RUST)
    d.polygon(_p([(165, 36 + bob), (170, 26 + bob), (173, 39 + bob)]), fill=BLACK)

    # Eye
    _ell(d, 172, 48 + bob, 178, 54 + bob, EYE)

    # Near legs on top.
    _leg(d, (back_hip[0] + 6, back_hip[1]), cycle + math.pi, front=False)
    _leg(d, (front_hip[0] + 6, front_hip[1]), cycle, front=True)

    return img.resize((W, H), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(FRAMES):
        _draw_fox(i).save(OUT / f"run_{i:02d}.png")
    print(f"Wrote {FRAMES} frames to {OUT}")


if __name__ == "__main__":
    main()
