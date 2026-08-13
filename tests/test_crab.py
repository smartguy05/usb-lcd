"""The crab widget.

Most of the coverage here is on the *pose* rather than on pixels. The animation
is a pure function of time, so sweeping a few minutes of simulated seconds and
asserting on properties — a blink happens, nothing jumps between frames, the
alarm is louder than every calm phase — says far more than pinning a golden
frame, and it runs in milliseconds because it renders nothing.

Anything that is not about motion renders with ``animate: False``, which pins the
clock at a fixed epoch. Those tests then have no time dependence at all and
cannot start flaking if the oscillator constants are retuned later.
"""

from datetime import datetime, timedelta, timezone

import pytest
from PIL import ImageChops

from usb_lcd_dashboard.layout import TileContext
from usb_lcd_dashboard.model import SessionState
from usb_lcd_dashboard.widgets.crab import _mix, crab_pose, render_crab


NOW = datetime(2026, 8, 6, 14, 37, 5, tzinfo=timezone.utc)
SIZES = [(486, 438), (438, 438), (480, 320), (300, 120), (120, 90)]

CRAB_PHASES = [
    "READY", "THINKING", "TOOL", "ACTIVE", "COMPACTING",
    "APPROVAL", "NOTICE", "ERROR", "DONE", "ENDED",
]
CALM_PHASES = ["READY", "TOOL", "ACTIVE", "THINKING", "DONE"]

STILL = {"animate": False}


def full_session(**kwargs):
    defaults = dict(
        provider="claude",
        session_id="one",
        updated_at=NOW,
        started_at=NOW - timedelta(minutes=7, seconds=12),
        phase="TOOL",
        activity="Editing src/usb_lcd_dashboard/widgets/crab.py",
        model="Claude Opus 5 (1M context)",
        cwd="/work/usb-lcd",
        context_percent=63.4,
    )
    return SessionState(**{**defaults, **kwargs})


def context(size, *, now=NOW, options=None, **kwargs):
    return TileContext(size=size, now=now, options=options or {}, **kwargs)


def still(size, **kwargs):
    options = {**STILL, **(kwargs.pop("options", None) or {})}
    return context(size, options=options, **kwargs)


def differs(a, b):
    """These tiles are RGBA with identical alpha, so colour differences need
    alpha_only=False — the same trap as in test_widgets.py."""
    return ImageChops.difference(a, b).getbbox(alpha_only=False) is not None


def sweep(phase, seconds, hz=20, **kwargs):
    return [crab_pose(phase, n / hz, **kwargs) for n in range(int(seconds * hz))]


# ------------------------------------------------- the mixer and the blinking

def test_the_blink_mixer_is_pinned():
    """Guards the schedule against someone reaching for hash().

    str and bytes hashing is salted per process, so a blink schedule built on it
    would differ between runs and could not be tested at all. This is plain
    integer arithmetic under a 64-bit mask, so it must hold everywhere.
    """
    assert _mix(0) == 0.0
    assert _mix(1) == pytest.approx(0.8833108082136427, abs=1e-12)
    assert _mix(12345) == pytest.approx(0.07923919782172156, abs=1e-12)
    assert all(0.0 <= _mix(n) <= 1.0 for n in range(500))


def test_the_crab_blinks():
    opens = [pose.eye_open for pose in sweep("READY", 20)]
    assert min(opens) < 0.15, "never blinked"
    assert max(opens) > 0.95, "never opened"
    # A crab that is shut a lot of the time reads as broken, not as sleepy.
    assert sum(1 for value in opens if value > 0.9) / len(opens) > 0.8


def test_blinks_are_irregular():
    """A fixed period reads as a machine; the gaps have to vary."""
    closed = [n for n, pose in enumerate(sweep("READY", 300)) if pose.eye_open < 0.5]
    assert closed, "never blinked in five minutes"
    onsets = [n for i, n in enumerate(closed) if i == 0 or n - closed[i - 1] > 4]
    assert len(onsets) >= 8
    gaps = {round((b - a) / 20, 1) for a, b in zip(onsets, onsets[1:])}
    assert len(gaps) >= 4, f"blink gaps are too regular: {sorted(gaps)}"


def test_the_alarm_never_blinks():
    """A blink is a moment of looking away, which an alarm cannot afford."""
    assert min(pose.eye_open for pose in sweep("APPROVAL", 60)) >= 1.0


# ------------------------------------------------------------------- the pose

@pytest.mark.parametrize("phase", CRAB_PHASES + [None])
def test_every_pose_stays_within_its_documented_range(phase):
    for pose in sweep(phase, 30):
        assert 0.0 <= pose.eye_open <= 1.25
        assert abs(pose.bob) <= 0.05
        assert abs(pose.lean) <= 0.20
        assert 0.85 <= pose.squash <= 1.06
        assert all(-40 <= claw <= 130 for claw in (pose.claw_l, pose.claw_r))
        assert all(0 <= gape <= 40 for gape in (pose.gape_l, pose.gape_r))
        assert all(abs(value) <= 1.0 for value in (pose.brow, pose.mouth))
        assert 0.0 <= pose.mouth_open <= 1.0
        assert 0.0 <= pose.border <= 1.0
        assert pose.glyph in {"", "!", "z"}


@pytest.mark.parametrize("phase", CRAB_PHASES)
def test_motion_is_continuous(phase):
    """Catches a wrapping clock: nothing may jump between adjacent frames.

    The bounds are set just above what the fastest oscillator legitimately does
    at 60 Hz — the alarm's claw peaks at about 5 deg per frame — and far below
    the tens of degrees a wrapped clock would jump. eye_open is held looser
    rather than exempted: a blink is meant to be fast, but a lid still must not
    teleport shut.
    """
    poses = [crab_pose(phase, n / 60) for n in range(600)]
    for before, after in zip(poses, poses[1:]):
        assert abs(after.bob - before.bob) < 0.004
        assert abs(after.claw_l - before.claw_l) < 6
        assert abs(after.claw_r - before.claw_r) < 6
        assert abs(after.mouth - before.mouth) < 0.1
        assert abs(after.eye_open - before.eye_open) < 0.35


def test_a_phase_change_does_not_rewind_the_crab():
    """TOOL and ACTIVE share an oscillator, so their bob stays in step.

    This is the regression guard on the whole no-state design. Give a phase its
    own epoch and the crab snaps every time the agent changes what it is doing;
    this is what notices.
    """
    for n in range(400):
        t = n / 20
        tool, active = crab_pose("TOOL", t).bob, crab_pose("ACTIVE", t).bob
        if abs(tool) > 1e-6 and abs(active) > 1e-6:
            assert (tool > 0) == (active > 0)


@pytest.mark.parametrize("phase", ["APPROVAL", "NOTICE"])
def test_the_alarm_is_louder_than_any_calm_phase(phase):
    def swing(name):
        poses = sweep(name, 12)
        return max(p.claw_l for p in poses) - min(p.claw_l for p in poses)

    alarm = sweep(phase, 12)
    assert all(pose.glyph == "!" for pose in alarm)
    assert max(pose.border for pose in alarm) > 0.9
    for calm in CALM_PHASES:
        assert swing(phase) > swing(calm)
        assert max(p.border for p in sweep(calm, 12)) == 0.0


def test_the_alarm_option_silences_the_border_but_not_the_crab():
    quiet = crab_pose("APPROVAL", 3.0, alarm=False)
    loud = crab_pose("APPROVAL", 3.0, alarm=True)
    assert quiet.border == 0.0 and loud.border > 0.0
    # The wave and the glyph still carry it.
    assert quiet.claw_l == loud.claw_l
    assert quiet.glyph == "!"


def test_a_sleeping_crab_is_shut_eyed():
    for phase in (None, "ENDED"):
        for pose in sweep(phase, 10):
            assert pose.eye_open < 0.2
            assert pose.glyph == "z"


# -------------------------------------------------------------------- shape

@pytest.mark.parametrize("size", SIZES)
def test_the_crab_fills_exactly_its_tile(size):
    image = render_crab(still(size, session=full_session(), slot=0))
    assert image.size == size
    assert image.mode == "RGBA"


@pytest.mark.parametrize("size", SIZES)
def test_a_crab_tile_with_no_session_renders(size):
    assert render_crab(still(size, session=None, slot=0)).size == size


@pytest.mark.parametrize("size", SIZES)
def test_a_crab_session_with_nothing_filled_in_still_renders(size):
    state = SessionState(
        provider="codex", session_id="bare", updated_at=NOW, started_at=NOW
    )
    assert render_crab(still(size, session=state, slot=0)).size == size


@pytest.mark.parametrize("phase", CRAB_PHASES)
def test_every_phase_renders_a_crab(phase):
    image = render_crab(still((486, 438), session=full_session(phase=phase), slot=0))
    assert image.size == (486, 438)


@pytest.mark.parametrize("percent", [None, 0, 0.4, 50, 99.9, 100])
def test_the_crab_context_bar_copes_with_every_percentage(percent):
    state = full_session(context_percent=percent)
    assert render_crab(still((486, 438), session=state, slot=0)).size == (486, 438)


@pytest.mark.parametrize("size", SIZES)
def test_the_crab_never_paints_over_the_edge_of_its_tile(size):
    # A calm phase, because the alarm border legitimately touches the edge.
    image = render_crab(
        still(size, session=full_session(phase="TOOL"), slot=0,
              options={"background": "transparent"})
    )
    bbox = image.getbbox(alpha_only=False)
    assert bbox is not None
    left, top, right, bottom = bbox
    assert left >= 0 and top >= 0
    assert right <= size[0] and bottom <= size[1]


# ---------------------------------------------------------------- animation

@pytest.mark.parametrize("phase", ["THINKING", "TOOL", "APPROVAL"])
def test_the_crab_moves_between_frames(phase):
    state = full_session(phase=phase)
    first = render_crab(context((486, 438), session=state, slot=0))
    later = render_crab(
        context((486, 438), now=NOW + timedelta(milliseconds=400), session=state, slot=0)
    )
    assert differs(first, later)


def test_animation_off_freezes_the_crab():
    state = full_session(phase="APPROVAL")
    first = render_crab(still((486, 438), session=state, slot=0))
    later = render_crab(
        context((486, 438), now=NOW + timedelta(seconds=37), options=STILL,
                session=state, slot=0)
    )
    assert not differs(first, later)


# ------------------------------------------------- the alarm reads as an alarm

def edge_alpha(image):
    """The border pulse is the only thing that paints the tile's outer edge."""
    return image.getpixel((2, image.height // 2))[3]


@pytest.mark.parametrize("phase", ["APPROVAL", "NOTICE"])
def test_the_alarm_paints_a_border(phase):
    image = render_crab(
        still((486, 438), session=full_session(phase=phase),
              options={"background": "transparent"})
    )
    assert edge_alpha(image) > 0


@pytest.mark.parametrize("phase", CALM_PHASES)
def test_a_calm_crab_paints_no_border(phase):
    image = render_crab(
        still((486, 438), session=full_session(phase=phase),
              options={"background": "transparent"})
    )
    assert edge_alpha(image) == 0


def test_the_alarm_option_removes_the_border_but_keeps_the_alarm():
    silenced = render_crab(
        still((486, 438), session=full_session(phase="APPROVAL"),
              options={"background": "transparent", "alarm": False})
    )
    calm = render_crab(
        still((486, 438), session=full_session(phase="READY"),
              options={"background": "transparent"})
    )
    assert edge_alpha(silenced) == 0
    assert differs(silenced, calm), "pose and colour must still carry the alarm"


def test_the_two_alarms_are_told_apart_by_colour():
    """Same urgency, different hue: warning yellow for an approval, Claude
    orange for a notification."""
    def border(phase):
        image = render_crab(
            still((486, 438), session=full_session(phase=phase),
                  options={"background": "transparent"})
        )
        return image.getpixel((2, 219))[:3]

    assert border("APPROVAL") != border("NOTICE")


# ------------------------------------------------------------ the size ladder

def test_a_cramped_tile_drops_the_text_rather_than_overflowing():
    state = full_session()
    with_text = render_crab(still((120, 90), session=state, options={"show_project": True}))
    without = render_crab(still((120, 90), session=state, options={"show_project": False}))
    assert not differs(with_text, without), "the label was drawn off-tile, not dropped"


def test_a_roomy_tile_honours_the_text_options():
    state = full_session()
    shown = render_crab(still((486, 438), session=state, options={"show_activity": True}))
    hidden = render_crab(still((486, 438), session=state, options={"show_activity": False}))
    assert differs(shown, hidden)


def test_a_tile_too_short_for_a_crab_falls_back_to_words():
    """Below the crab's floor a mascot is a smudge, so say the phase instead."""
    editing = render_crab(still((486, 40), session=full_session(activity="Editing crab.py")))
    running = render_crab(still((486, 40), session=full_session(activity="Running the build")))
    assert editing.size == (486, 40)
    assert differs(editing, running)


def test_the_colour_option_overrides_the_provider():
    state = full_session()
    default = render_crab(still((486, 438), session=state))
    green = render_crab(still((486, 438), session=state, options={"color": "#2bc48a"}))
    assert differs(default, green)


def test_the_context_bar_can_be_turned_off():
    state = full_session()
    shown = render_crab(still((486, 438), session=state, options={"show_context": True}))
    hidden = render_crab(still((486, 438), session=state, options={"show_context": False}))
    assert differs(shown, hidden)
