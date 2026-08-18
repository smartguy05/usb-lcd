"""A session as an animated crab.

The agent card tells you everything and catches your eye with nothing. This is
the other half of that trade: a crab in Claude orange that bobs, blinks, scuttles
and — when the agent is waiting on you — waves both claws over its head behind a
pulsing border, which is visible from across a room in a way that the words
"APPROVAL NEEDED" are not.

Three things shape the implementation.

**There is no per-widget state.** ``TileContext`` is frozen and a widget is a
plain function, so every moving part is a pure function of ``ctx.now``. That is
not a workaround: it means the animation has no epoch to drift, a session moved
between tiles never restarts mid-stride, and any frame is reproducible in a test
by naming its timestamp.

**Phase changes must not rewind the crab.** The oscillators below have fixed
frequencies and a fixed epoch, and a phase changes only their *coefficients*. A
crab halfway through a breath stays halfway through it across READY -> TOOL ->
DONE. Where a discontinuity is wanted — anything -> APPROVAL — it reads as a snap
to attention, which is the point.

**ImageDraw does not antialias**, and this is nothing but curves and thin
diagonal limbs. Everything is drawn supersampled and box-filtered down; see
``_supersample`` for why that is ``reduce()`` and not ``resize()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, radians, sin

from PIL import Image, ImageColor, ImageDraw

from ..layout import TileContext
from ..render import (
    BACKGROUND,
    CLAUDE,
    CODEX,
    ERROR,
    MUTED,
    TEXT,
    WARNING,
    _branch,
    _fit,
    _fit_headline,
    _font,
)
from .base import context_bar, new_tile

# The crab is wider than it is tall, as a crab is.
ASPECT = 1.35

# Below this the crab is a smudge rather than an animal, and the tile is better
# served by the phase word.
MIN_CRAB_HEIGHT = 44

ALARM_PHASES = frozenset({"APPROVAL", "NOTICE"})
SLEEPING_PHASES = frozenset({"ENDED"})


# --------------------------------------------------------------------- the pose


@dataclass(frozen=True, slots=True)
class CrabPose:
    """Everything about the crab that moves, as plain numbers.

    Kept separate from the drawing so the animation can be tested by sweeping
    time and asserting on values, rather than by pinning pixels.
    """

    bob: float = 0.0          # vertical offset in units of box height, + is down
    lean: float = 0.0         # shear about the ground line, + leans right
    squash: float = 1.0       # scales the shell's height; < 1 crouches
    eye_open: float = 1.0     # 0 shut .. 1 normal .. 1.25 alarmed
    happy_eyes: bool = False  # draw "^ ^" instead of eyeballs
    pupil_dx: float = 0.0     # -1 .. 1 of the free travel inside the eye
    pupil_dy: float = 0.0
    claw_l: float = 0.0       # arm elevation in degrees; - drooped, + raised
    claw_r: float = 0.0
    gape_l: float = 0.0       # pincer opening in degrees
    gape_r: float = 0.0
    brow: float = 0.0         # -1 raised/surprised .. +1 furrowed/angry
    mouth: float = 0.0        # -1 frown .. +1 smile; near zero draws flat
    mouth_open: float = 0.0   # 0 .. 1; past 0.15 becomes an "O"
    leg_phase: float = 0.0    # radians through the walk cycle
    leg_amp: float = 0.0      # degrees of knee swing; 0 is planted
    glyph: str = ""           # "" | "!" | "z"
    glyph_pulse: float = 0.0  # 0 .. 1, scales the glyph
    border: float = 0.0       # 0 .. 1 alarm border intensity
    sweep: float = -1.0       # 0 .. 1 position of the COMPACTING sweep; < 0 off


# ------------------------------------------------------------------ the clock

_MASK = (1 << 64) - 1

BLINK_BUCKET = 3.0
BLINK_DURATION = 0.16


def _mix(n: int) -> float:
    """splitmix64, returning 0..1.

    Written out rather than reaching for ``hash()`` or ``random``: str and bytes
    hashing is salted per process by PYTHONHASHSEED, so a blink schedule built on
    it would differ between runs and could not be tested. This is pure integer
    arithmetic under a 64-bit mask, so it is identical on every platform and
    every Python version.
    """
    x = (n * 0x9E3779B97F4A7C15) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return ((x ^ (x >> 31)) & _MASK) / 2**64


def _blink_shape(dt: float) -> float:
    """How open the eye is ``dt`` seconds into a blink."""
    if not 0.0 <= dt <= BLINK_DURATION:
        return 1.0
    # Slightly past linear, so the lid drops faster than it lifts.
    return abs(2 * (dt / BLINK_DURATION) - 1) ** 0.7


def _eye_open(t: float, rate: float) -> float:
    """A blink schedule that looks irregular but is a pure function of time.

    Time is bucketed; each bucket either holds a blink or does not, and the
    offset *within* the bucket is pseudorandom. That gives gaps ranging from a
    fraction of a second to several seconds, plus the occasional double blink,
    without a period a viewer can start predicting. The previous bucket is
    checked too so a blink that straddles a boundary is not clipped.
    """
    if rate <= 0:
        return 1.0
    current = int(t // BLINK_BUCKET)
    open_amount = 1.0
    for bucket in (current, current - 1):
        if _mix(bucket * 3 + 1) > rate:
            continue
        start = bucket * BLINK_BUCKET + _mix(bucket) * (
            BLINK_BUCKET - BLINK_DURATION - 0.25
        )
        open_amount = min(open_amount, _blink_shape(t - start))
        if _mix(bucket ^ 0x5BF0) < 0.22:
            open_amount = min(open_amount, _blink_shape(t - start - 0.24))
    return open_amount


def _oscillators(t: float) -> tuple[float, float, float, float, float]:
    """The whole animation's motive power.

    Fixed frequencies and a fixed epoch, deliberately: a phase change swaps only
    the coefficients applied to these, so nothing rewinds when the agent moves
    from thinking to running a tool.

    Nothing here exceeds 0.63 Hz, and the ceiling is set by the panel rather
    than by taste. The 3.5" Turing screen is a 115200-baud serial link, and the
    frame rate it sustains is set by how many pixels changed: measured, a crab
    that redraws its own box manages about 2.2 fps. A wave needs roughly four
    samples per cycle to read as a wave rather than as the claws teleporting, so
    anything faster than ~0.55 Hz is not merely wasted on this hardware, it
    actively looks worse. The alarm therefore waves at the same rate the crab
    works at, and carries its urgency through pose, colour and the glyph.
    """
    return (
        sin(2 * pi * t / 4.00),          # 0.25 Hz  breathing
        sin(2 * pi * t / 1.60),          # 0.63 Hz  working
        sin(2 * pi * t / 1.80),          # 0.56 Hz  alarm
        sin(2 * pi * t / 1.60 + pi),     # 0.63 Hz  counter-phase partner
        sin(2 * pi * t / 9.00 + 1.1),    # 0.11 Hz  slow gaze drift
    )


def _unit(value: float) -> float:
    """An oscillator remapped from -1..1 to 0..1."""
    return (value + 1.0) / 2.0


def crab_pose(phase: str | None, t: float, *, alarm: bool = True) -> CrabPose:
    """The crab's pose for a phase at an absolute time.

    ``t`` is POSIX seconds — monotone, DST-free and machine-independent. Never
    build this from ``now.second``, which wraps at 60 and would snap the crab
    once a minute.
    """
    s1, s2, s3, s4, s5 = _oscillators(t)

    if phase is None:
        return CrabPose(
            bob=0.008 * s1,
            eye_open=0.06 + 0.03 * _unit(s1),
            claw_l=-18, claw_r=-18, gape_l=3, gape_r=3,
            brow=-0.1,
            glyph="z", glyph_pulse=_unit(s1),
        )

    if phase in ALARM_PHASES:
        # Four cues at once — motion, silhouette, colour and glyph — because a
        # single one is missable on a panel nobody is looking at.
        return CrabPose(
            bob=0.022 * abs(s3),
            eye_open=1.15,
            pupil_dx=0.15 * s3,
            # Splayed outward and kept below vertical: past 90 degrees the
            # forearm folds inward and the claw ends up poking the eyestalk,
            # which muddles the silhouette exactly when it matters most.
            claw_l=62 + 26 * s3,
            claw_r=62 - 26 * s3,
            gape_l=8 + 18 * _unit(s3),
            gape_r=8 + 18 * _unit(-s3),
            brow=-0.45,
            mouth_open=0.55 + 0.35 * _unit(s3),
            glyph="!", glyph_pulse=_unit(s3),
            # Deliberately constant, not pulsing. The panel is only sent the
            # rectangle that changed between frames, and a border that breathes
            # is a change at the tile's outer edge — so it dirties the whole
            # tile every frame and triples the bytes over the serial link at the
            # one moment responsiveness matters. Measured on the 3.5" panel: a
            # pulsing border drops 2.2fps to 0.8fps, at which point the "pulse"
            # is slower than the frame rate and reads as random flicker anyway.
            # The claws, the glyph and the eyes carry the motion; the border
            # just has to be unmistakably there.
            border=1.0 if alarm else 0.0,
        )

    if phase == "ERROR":
        return CrabPose(
            bob=0.006 * s3,
            lean=-0.10,
            eye_open=min(0.55, _eye_open(t, 0.2)),
            pupil_dy=0.7,
            claw_l=-30 + 4 * s3, claw_r=-30 - 4 * s3,
            gape_l=1, gape_r=1,
            brow=0.65,
            mouth=-0.8,
        )

    if phase == "DONE":
        return CrabPose(
            bob=0.008 * s1,
            happy_eyes=True,
            claw_l=10 + 3 * s1, claw_r=10 + 3 * s1,
            gape_l=2, gape_r=2,
            brow=-0.15,
            mouth=0.90,
        )

    if phase in SLEEPING_PHASES:
        return CrabPose(
            bob=0.006 * s1,
            eye_open=0.05,
            claw_l=-22, claw_r=-22, gape_l=2, gape_r=2,
            glyph="z", glyph_pulse=_unit(s1),
        )

    if phase == "COMPACTING":
        return CrabPose(
            bob=-0.018 * _unit(s1),
            squash=1 - 0.07 * _unit(s2),
            eye_open=0.45 + 0.15 * _unit(s2),
            claw_l=-25, claw_r=-25, gape_l=2, gape_r=2,
            brow=0.2,
            sweep=(t % 2.0) / 2.0,
        )

    if phase == "THINKING":
        return CrabPose(
            bob=0.012 * s2,
            eye_open=_eye_open(t, 0.30),
            pupil_dx=-0.50 + 0.35 * s5,
            pupil_dy=-0.60,
            claw_l=4,
            claw_r=55 + 7 * s2,          # a claw up at the chin
            gape_l=4,
            gape_r=4 + 12 * _unit(s2),
            brow=0.30,
            mouth=-0.10,
        )

    if phase == "TOOL":
        return CrabPose(
            bob=0.014 * s2,
            eye_open=_eye_open(t, 0.60),
            pupil_dy=0.25,
            claw_l=20 + 22 * s2,
            claw_r=20 + 22 * s4,
            gape_l=6 + 10 * _unit(s2),
            gape_r=6 + 10 * _unit(s4),
            brow=0.15,
            leg_phase=2 * pi * t / 1.6,
            leg_amp=10,
        )

    if phase == "READY":
        return CrabPose(
            bob=0.010 * s1,
            eye_open=_eye_open(t, 0.75),
            pupil_dx=0.55 * s5,
            pupil_dy=0.20 * s1,
            claw_l=6 + 4 * s1, claw_r=6 + 4 * s1,
            gape_l=4, gape_r=4,
            mouth=0.25,
        )

    # ACTIVE, and anything the normaliser invents later: a calmer TOOL.
    return CrabPose(
        bob=0.010 * s2,
        eye_open=_eye_open(t, 0.70),
        pupil_dy=0.25,
        claw_l=14 + 11 * s2,
        claw_r=14 + 11 * s4,
        gape_l=5 + 6 * _unit(s2),
        gape_r=5 + 6 * _unit(s4),
    )


# ------------------------------------------------------------------ the drawing


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    """Rotate a vector, positive degrees reading as anticlockwise on screen.

    The sign flip is because the raster's y axis points down.
    """
    angle = radians(degrees)
    return (
        x * cos(angle) + y * sin(angle),
        -x * sin(angle) + y * cos(angle),
    )


def _shade(colour: str, factor: float) -> tuple[int, int, int]:
    """Lighten (factor > 0) or darken (factor < 0) towards white or black."""
    red, green, blue = ImageColor.getrgb(colour)[:3]
    if factor >= 0:
        return tuple(round(c + (255 - c) * factor) for c in (red, green, blue))
    return tuple(round(c * (1 + factor)) for c in (red, green, blue))


class _Frame:
    """Maps the crab's unit coordinates onto a pixel box.

    Limb geometry works in units of the box's *short* side so a claw is not
    stretched when the tile is not the crab's native aspect, while body
    landmarks stay proportional to the box. Bob and lean are folded in here so
    no part of the rig has to think about them.
    """

    __slots__ = ("x0", "y0", "width", "height", "short", "bob", "lean")

    def __init__(self, box: tuple[float, float, float, float], pose: CrabPose):
        self.x0, self.y0, x1, y1 = box
        self.width = x1 - self.x0
        self.height = y1 - self.y0
        self.short = min(self.width, self.height)
        self.bob = pose.bob
        self.lean = pose.lean

    def at(self, u: float, v: float) -> tuple[float, float]:
        shifted = v + self.bob
        # Shear about the ground line, so the feet stay put and the body tips.
        skew = self.lean * (0.92 - shifted) * self.width
        return (self.x0 + u * self.width + skew, self.y0 + shifted * self.height)

    def box(self, u0: float, v0: float, u1: float, v1: float):
        left, top = self.at(u0, v0)
        right, bottom = self.at(u1, v1)
        return (left, top, right, bottom)

    def polar(self, radius: float, degrees: float) -> tuple[float, float]:
        """A limb offset in pixels; positive degrees point up-and-out."""
        return (
            radius * self.short * cos(radians(degrees)),
            -radius * self.short * sin(radians(degrees)),
        )

    def stroke(self, weight: float, floor: int = 1) -> int:
        return max(floor, round(weight * self.short))


# The pincer, as offsets from the wrist in units of the short side. Two jaws
# that share a hinge: rotating only the second by the gape angle opens it.
_JAW_FIXED = [(0.00, -0.014), (0.100, -0.058), (0.150, -0.030), (0.062, 0.004)]
_JAW_MOVING = [(0.00, 0.014), (0.100, 0.058), (0.150, 0.030), (0.062, -0.004)]


def _draw_claw(
    draw: ImageDraw.ImageDraw,
    frame: _Frame,
    shoulder: tuple[float, float],
    elevation: float,
    gape: float,
    colour,
    outward: int,
) -> None:
    """One arm and its pincer, at any elevation and any opening.

    Built in a local frame where +x points away from the body and mirrored by
    ``outward``, which is what keeps this one function serving both sides.
    """

    def place(offset: tuple[float, float], origin: tuple[float, float]):
        return (origin[0] + outward * offset[0], origin[1] + offset[1])

    elbow = place(frame.polar(0.14, elevation), shoulder)
    forearm_angle = elevation - 25
    wrist = place(frame.polar(0.12, forearm_angle), elbow)

    draw.line(
        [shoulder, elbow, wrist],
        fill=colour,
        width=frame.stroke(0.038, 2),
        joint="curve",
    )
    knuckle = frame.short * 0.038
    draw.ellipse(
        (wrist[0] - knuckle, wrist[1] - knuckle, wrist[0] + knuckle, wrist[1] + knuckle),
        fill=colour,
    )

    for jaw, angle in ((_JAW_FIXED, forearm_angle), (_JAW_MOVING, forearm_angle + gape)):
        points = []
        for px, py in jaw:
            rx, ry = _rotate(px * frame.short, py * frame.short, angle)
            points.append((wrist[0] + outward * rx, wrist[1] + ry))
        draw.polygon(points, fill=colour)


def _draw_legs(
    draw: ImageDraw.ImageDraw, frame: _Frame, pose: CrabPose, colour, count: int
) -> None:
    """Three legs a side, each a knee-and-foot polyline.

    The legs are phase-shifted thirds of one cycle, so a walking crab's feet
    land in sequence rather than all at once.
    """
    roots = [(0.26, 0.62), (0.235, 0.70), (0.26, 0.765)][:count]
    width = frame.stroke(0.024, 1)
    ground = frame.at(0.5, 0.92)[1]
    for index, (left_u, v) in enumerate(roots):
        swing = pose.leg_amp * sin(pose.leg_phase + index * 2 * pi / 3)
        knee_dx, knee_dy = frame.polar(0.090, 38 + swing)
        foot_dx, foot_dy = frame.polar(0.075, -70 + swing * 0.5)
        for outward in (-1, 1):
            root = frame.at(left_u if outward < 0 else 1.0 - left_u, v)
            knee = (root[0] + outward * knee_dx, root[1] + knee_dy)
            foot = (knee[0] + outward * foot_dx, min(ground, knee[1] + foot_dy))
            draw.line([root, knee, foot], fill=colour, width=width, joint="curve")


def _draw_sweep(draw: ImageDraw.ImageDraw, shell, position: float, fill) -> None:
    """A vertical band of light crossing the shell, clipped to it.

    Clipped by construction rather than by a mask layer: the band is a polygon
    that follows the ellipse's own top and bottom edges across its x range, so
    it cannot spill past the shell and no second image is needed.
    """
    left, top, right, bottom = shell
    rx, ry = (right - left) / 2, (bottom - top) / 2
    if rx <= 0 or ry <= 0:
        return
    cx, cy = left + rx, top + ry
    span = right - left
    start = left + position * span
    end = min(right, start + span * 0.16)
    if end - start < 1:
        return

    steps = 12
    top_edge, bottom_edge = [], []
    for step in range(steps + 1):
        x = start + (end - start) * step / steps
        offset = min(1.0, abs(x - cx) / rx)
        half = ry * (1 - offset**2) ** 0.5
        top_edge.append((x, cy - half))
        bottom_edge.append((x, cy + half))
    draw.polygon(top_edge + list(reversed(bottom_edge)), fill=fill)


def _draw_eye(
    draw: ImageDraw.ImageDraw,
    frame: _Frame,
    centre_u: float,
    pose: CrabPose,
    colour,
) -> None:
    alarmed = pose.eye_open > 1.0
    radius = (0.085 if not alarmed else 0.095) * frame.short
    cx, cy = frame.at(centre_u, 0.155)

    if pose.happy_eyes:
        # The classic content "^", far more legible at 60px than a shut eyeball.
        # It needs the body-coloured ball behind it: the caret is dark, and on a
        # bare canvas it would be dark-on-dark and vanish.
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=colour)
        box = (cx - radius * 0.72, cy - radius * 0.25, cx + radius * 0.72, cy + radius * 0.95)
        draw.arc(box, 200, 340, fill=BACKGROUND, width=frame.stroke(0.020, 2))
        return

    eye = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.ellipse(eye, fill=TEXT)

    pupil = (0.038 if not alarmed else 0.027) * frame.short
    px = cx + pose.pupil_dx * 0.030 * frame.short
    py = cy + pose.pupil_dy * 0.028 * frame.short
    draw.ellipse((px - pupil, py - pupil, px + pupil, py + pupil), fill=BACKGROUND)

    if pose.eye_open < 1.0:
        # A lid coming down, rather than a squashed eye: at partial values a lid
        # reads as sleepy, where a squash just reads as a smaller eye.
        lid = cy - radius + (1.0 - pose.eye_open) * 2 * radius
        draw.rectangle((cx - radius, cy - radius, cx + radius, lid), fill=colour)
        draw.ellipse(eye, outline=colour, width=frame.stroke(0.010, 1))
        if pose.eye_open <= 0.02:
            draw.line(
                (cx - radius * 0.75, cy, cx + radius * 0.75, cy),
                fill=BACKGROUND,
                width=frame.stroke(0.014, 1),
            )


def _draw_mouth(draw: ImageDraw.ImageDraw, frame: _Frame, pose: CrabPose) -> None:
    left, top, right, bottom = frame.box(0.42, 0.635, 0.58, 0.725)
    if pose.mouth_open > 0.15:
        half_w = (right - left) / 2 * 0.7
        half_h = (bottom - top) / 2 * pose.mouth_open
        cx, cy = (left + right) / 2, (top + bottom) / 2
        draw.ellipse((cx - half_w, cy - half_h, cx + half_w, cy + half_h), fill=BACKGROUND)
        return

    width = frame.stroke(0.016, 1)
    if abs(pose.mouth) <= 0.2:
        cy = (top + bottom) / 2
        draw.line((left, cy, right, cy), fill=BACKGROUND, width=width)
        return

    # Squeeze the box by how strong the expression is, so 0.25 is a hint of a
    # smile and 0.9 a broad one.
    height = (bottom - top) * min(1.0, abs(pose.mouth))
    cy = (top + bottom) / 2
    box = (left, cy - height / 2, right, cy + height / 2)
    draw.arc(box, 0 if pose.mouth > 0 else 180, 180 if pose.mouth > 0 else 360,
             fill=BACKGROUND, width=width)


def draw_crab(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    pose: CrabPose,
    colour: str,
    *,
    detail: str = "full",
) -> None:
    """Draw the crab into ``box``, back to front.

    Resolution-agnostic on purpose: it never knows whether it is being drawn
    supersampled, which is what lets the still-image path skip that cost and
    what keeps it directly unit-testable.
    """
    frame = _Frame(box, pose)
    body = ImageColor.getrgb(colour)[:3] + (255,)

    if detail == "full":
        draw.ellipse(frame.box(0.28, 0.885, 0.72, 0.955), fill=(0, 0, 0, 60))

    if detail != "mini":
        _draw_legs(draw, frame, pose, body, 3 if detail == "full" else 2)

    # Claws go behind the shell so the shoulder joint is hidden and a claw can
    # wave overhead without a seam where it crosses the body.
    for shoulder_u, elevation, gape, outward in (
        (0.24, pose.claw_l, pose.gape_l, -1),
        (0.76, pose.claw_r, pose.gape_r, 1),
    ):
        _draw_claw(draw, frame, frame.at(shoulder_u, 0.58), elevation, gape, body, outward)

    crouch = 0.22 * (1 - pose.squash)
    shell = frame.box(0.20, 0.34 + crouch, 0.80, 0.78)
    draw.ellipse(shell, fill=body)
    draw.arc(shell, 180, 360, fill=_shade(colour, -0.25), width=frame.stroke(0.014, 1))

    if pose.sweep >= 0.0:
        _draw_sweep(draw, shell, pose.sweep, _shade(colour, 0.30) + (255,))

    _draw_mouth(draw, frame, pose)

    stalk_half = 0.0275
    for centre_u in (0.395, 0.605):
        left, top = frame.at(centre_u - stalk_half, 0.155)
        right, bottom = frame.at(centre_u + stalk_half, 0.44)
        draw.rounded_rectangle(
            (left, top, right, bottom), radius=frame.stroke(0.028, 1), fill=body
        )

    for centre_u in (0.395, 0.605):
        _draw_eye(draw, frame, centre_u, pose, body)

    if detail == "full" and not pose.happy_eyes:
        width = frame.stroke(0.016, 1)
        for centre_u, inward in ((0.395, 1), (0.605, -1)):
            cx, cy = frame.at(centre_u, 0.155)
            radius = 0.085 * frame.short
            lift = 0.022 * frame.short * pose.brow
            span = 0.075 * frame.short
            top = cy - radius - 0.030 * frame.short
            draw.line(
                (cx - inward * span, top + lift, cx + inward * span, top - lift),
                fill=_shade(colour, -0.35),
                width=width,
            )

    if detail == "full":
        # Opaque, not translucent: ImageDraw replaces rather than blends, so an
        # alpha fill here would punch a hole in the shell instead of lighting it.
        draw.ellipse(frame.box(0.315, 0.395, 0.44, 0.465), fill=_shade(colour, 0.22) + (255,))


def _supersample(size: tuple[int, int], pose: CrabPose, colour: str, detail: str) -> Image.Image:
    """Draw the crab oversized and box-filter it down.

    ``reduce()`` rather than ``resize()``: it is an exact integer box filter,
    which is the correct answer for supersampling, it does not ring the way
    LANCZOS does around the dark pupil, and it measures about twice as fast.

    The canvas is prefilled with the crab's own RGB at zero alpha rather than
    transparent black. Averaging happens on straight-alpha RGBA, so transparent
    *black* neighbours drag the silhouette's edge pixels toward black and leave a
    dark halo; prefilling means only alpha varies across that edge.
    """
    width, height = size
    factor = 4 if height <= 90 else 3 if height <= 200 else 2
    canvas = Image.new("RGBA", (width * factor, height * factor),
                       ImageColor.getrgb(colour)[:3] + (0,))
    draw_crab(
        ImageDraw.Draw(canvas),
        (0, 0, width * factor, height * factor),
        pose,
        colour,
        detail=detail,
    )
    return canvas.reduce(factor)


# ------------------------------------------------------------------- the widget


def _colour_for(phase: str | None, provider: str, override: str) -> str:
    if override:
        return override
    if phase is None or phase in SLEEPING_PHASES:
        return MUTED
    if phase == "ERROR":
        return ERROR
    return CLAUDE if provider != "codex" else CODEX


def _accent_for(phase: str | None) -> str:
    if phase == "APPROVAL":
        return WARNING
    if phase == "NOTICE":
        return CLAUDE
    if phase == "ERROR":
        return ERROR
    return CLAUDE


def _detail_for(height: int) -> str:
    if height >= 110:
        return "full"
    if height >= 60:
        return "mid"
    return "mini"


def _paste_crab(image: Image.Image, region, pose: CrabPose, colour: str) -> None:
    """Fit the crab into ``region`` at its native aspect and composite it."""
    left, top, right, bottom = region
    available_w, available_h = right - left, bottom - top
    height = min(available_h, available_w / ASPECT)
    width = height * ASPECT
    if height < MIN_CRAB_HEIGHT:
        return
    width, height = round(width), round(height)
    x = round(left + (available_w - width) / 2)
    y = round(top + (available_h - height) / 2)
    image.alpha_composite(_supersample((width, height), pose, colour, _detail_for(height)), (x, y))


def _draw_glyph(draw, pose: CrabPose, region, accent: str, short: int) -> None:
    if not pose.glyph:
        return
    left, top, right, bottom = region
    size = max(10, round(short * 0.22 * (0.85 + 0.3 * pose.glyph_pulse)))
    draw.text(
        (right - short * 0.06, top + short * 0.10),
        pose.glyph,
        font=_font(size, True),
        fill=accent,
        anchor="ma",
    )


def render_crab(ctx: TileContext) -> Image.Image:
    state = ctx.session
    options = ctx.options
    width, height = ctx.size
    image, draw = new_tile(ctx.size, options, ctx.card_opacity)

    phase = state.phase if state is not None else None
    provider = state.provider if state is not None else ""
    alarm_enabled = bool(options.get("alarm", True))
    animate = bool(options.get("animate", True))
    # A fixed epoch pins every oscillator at a canonical value, which is both the
    # still-picture mode and what makes the pixel tests time-independent.
    t = ctx.now.timestamp() if animate else 0.0

    pose = crab_pose(phase, t, alarm=alarm_enabled)
    colour = _colour_for(phase, provider, str(options.get("color", "") or ""))
    accent = _accent_for(phase)

    pad = max(6, round(min(width, height) * 0.05))
    inner = max(1, width - 2 * pad)
    right = width - pad

    show_project = bool(options.get("show_project", True)) and state is not None
    show_activity = bool(options.get("show_activity", True)) and state is not None
    show_context = bool(options.get("show_context", True))

    percent = state.context_percent if state is not None else None
    activity = ""
    if state is not None:
        activity = state.activity if state.activity else state.phase

    if height >= 260 and width >= 200:
        region = (pad, round(height * 0.05), right, round(height * 0.60))
        if show_project:
            label = state.project
            branch = _branch(state.cwd)
            if branch:
                label = f"{label}  ·  {branch}"
            text, font = _fit(draw, label, inner, max(10, round(height * 0.075)), True, min_size=10)
            draw.text((pad, round(height * 0.655)), text, font=font, fill=TEXT)
        if show_activity:
            text, font = _fit(draw, activity, inner, max(9, round(height * 0.058)), min_size=9)
            draw.text((pad, round(height * 0.755)), text, font=font, fill=MUTED)
        if show_context:
            context_bar(
                draw,
                (pad, round(height * 0.845), right, round(height * 0.905) + max(6, round(height * 0.044))),
                percent,
                accent,
                label_size=max(9, round(height * 0.047)),
            )
    elif height >= 160:
        region = (pad, round(height * 0.05), right, round(height * 0.50))
        if show_project:
            label, font = _fit(draw, state.project, round(inner * 0.7),
                               max(10, round(height * 0.085)), True, min_size=9)
            draw.text((pad, round(height * 0.58)), label, font=font, fill=TEXT)
            draw.text((right, round(height * 0.58)),
                      f"{percent:.0f}%" if percent is not None else "—",
                      font=_font(max(9, round(height * 0.075)), True), fill=TEXT, anchor="ra")
        if show_activity:
            text, font = _fit(draw, activity, inner, max(9, round(height * 0.068)), min_size=8)
            draw.text((pad, round(height * 0.71)), text, font=font, fill=MUTED)
        if show_context:
            context_bar(
                draw,
                (pad, round(height * 0.86), right, height - pad),
                percent,
                accent,
                label_size=0,
            )
    elif height >= 110 and width >= 140:
        # A vertical stack here would leave the crab about 40px. Put it beside
        # the text instead.
        crab_w = min(round(width * 0.38), round((height - 2 * pad) * ASPECT))
        region = (pad, pad, pad + crab_w, height - pad)
        column = pad + crab_w + max(6, round(width * 0.03))
        column_width = max(1, right - column)
        if show_project:
            label, font = _fit(draw, state.project, round(column_width * 0.62),
                               max(10, round(height * 0.15)), True, min_size=9)
            draw.text((column, round(height * 0.20)), label, font=font, fill=TEXT)
            draw.text((right, round(height * 0.20)),
                      f"{percent:.0f}%" if percent is not None else "—",
                      font=_font(max(9, round(height * 0.13)), True), fill=TEXT, anchor="ra")
        if show_context:
            context_bar(
                draw,
                (column, round(height * 0.60), right, round(height * 0.78)),
                percent,
                accent,
                label_size=0,
            )
    else:
        # At this size the crab *is* the status: phase colour and posture carry
        # it, and any text would be unreadable anyway.
        sliver = max(3, round(height * 0.05)) if height >= 70 and show_context else 0
        region = (pad, pad, right, height - pad - (sliver + 3 if sliver else 0))
        if sliver:
            context_bar(
                draw,
                (pad, height - pad - sliver, right, height - pad),
                percent,
                accent,
                label_size=0,
            )

    if region[3] - region[1] >= MIN_CRAB_HEIGHT and (region[2] - region[0]) >= MIN_CRAB_HEIGHT * 0.7:
        _paste_crab(image, region, pose, colour)
        _draw_glyph(draw, pose, region, accent, min(width, height))
    else:
        # No room for an animal. Say the phase instead of drawing a smudge.
        lines, font = _fit_headline(draw, activity or "IDLE", inner,
                                    max_size=max(10, round((region[3] - region[1]) * 0.8)))
        line_height = round(getattr(font, "size", 12) * 1.2)
        for index, line in enumerate(lines):
            draw.text((pad, region[1] + index * line_height), line, font=font, fill=accent)

    if pose.border > 0.0:
        radius = max(4, round(min(width, height) * 0.05))
        outline = ImageColor.getrgb(accent)[:3] + (round(140 + 115 * pose.border),)
        draw.rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=radius,
            outline=outline,
            width=1 + round(3 * pose.border),
        )

    return image
