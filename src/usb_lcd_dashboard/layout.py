from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from PIL import Image, ImageDraw

from .background import Background, background_layer
from .model import SessionState
from .messaging import MessageSnapshot
from .notifications import NotificationSnapshot
from .todos import TodoSnapshot
from .render import ERROR, MUTED, PANEL, _fit

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Tile:
    """A rectangle of the panel and the widget that owns it.

    Rects are explicit pixels rather than a column grid: 1920x462 does not divide
    into whole squares, and the panels differ enough that a layout is not
    portable between them anyway. Each machine keeps its own config.
    """

    widget: str
    x: int
    y: int
    w: int
    h: int
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> tuple[int, int]:
        return (self.w, self.h)

    @property
    def origin(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def rect(self) -> tuple[int, int, int, int]:
        """left, top, right, bottom — right/bottom exclusive, as Pillow wants."""
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass(frozen=True, slots=True)
class TileContext:
    size: tuple[int, int]
    now: datetime
    options: dict[str, Any]
    session: SessionState | None = None
    slot: int = -1
    connected: bool = True
    idle_title: str = ""
    messages: MessageSnapshot | None = None
    notifications: NotificationSnapshot | None = None
    todos: TodoSnapshot | None = None


def _overlap(a: Tile, b: Tile) -> bool:
    # A shared edge is not an overlap: abutting tiles are a normal layout.
    return (
        a.x < b.x + b.w
        and b.x < a.x + a.w
        and a.y < b.y + b.h
        and b.y < a.y + a.h
    )


def validate(tiles: Sequence[Tile], size: tuple[int, int]) -> None:
    """Reject a broken layout at config-load time, not at frame time."""
    from .widgets import WIDGETS

    if not tiles:
        raise ValueError("layout needs at least one tile")
    width, height = size
    for index, tile in enumerate(tiles):
        where = f"tile[{index}] ({tile.widget})"
        if tile.widget not in WIDGETS:
            known = ", ".join(sorted(WIDGETS))
            raise ValueError(f"{where} is not a known widget; known widgets: {known}")
        if tile.w <= 0 or tile.h <= 0:
            raise ValueError(f"{where} has a non-positive size {tile.w}x{tile.h}")
        if tile.x < 0 or tile.y < 0:
            raise ValueError(f"{where} starts off screen at ({tile.x}, {tile.y})")
        if tile.x + tile.w > width or tile.y + tile.h > height:
            raise ValueError(
                f"{where} at {tile.rect} does not fit the {width}x{height} display"
            )
        if tile.widget == "notifications" and "rotation_seconds" in tile.options:
            try:
                rotation_seconds = float(tile.options["rotation_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{where} rotation_seconds must be a number") from exc
            if not 1 <= rotation_seconds <= 300:
                raise ValueError(f"{where} rotation_seconds must be between 1 and 300")
    for index, tile in enumerate(tiles):
        for other_index in range(index + 1, len(tiles)):
            other = tiles[other_index]
            if _overlap(tile, other):
                raise ValueError(
                    f"tile[{index}] ({tile.widget}) at {tile.rect} overlaps "
                    f"tile[{other_index}] ({other.widget}) at {other.rect}"
                )


def agent_slots(tiles: Sequence[Tile]) -> int:
    """How many sessions can be on screen at once.

    Counted from the layout rather than configured separately: a standalone
    number could only ever disagree with the tiles, leaving a permanently blank
    tile or silently discarding an assignment.
    """
    from .widgets import WIDGETS

    return sum(1 for tile in tiles if WIDGETS[tile.widget].wants_session)


def _fault_tile(size: tuple[int, int], widget: str) -> Image.Image:
    """What a tile shows when its widget raised.

    One broken widget must not cost the whole frame. The daemon used to drop the
    entire image on any render fault, which with several tiles means losing three
    working ones to fix nothing.
    """
    image = Image.new("RGBA", size, PANEL)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=8, outline=ERROR)
    label, font = _fit(draw, f"{widget} ERROR", max(1, size[0] - 16), 16, True)
    draw.text((8, 8), label, font=font, fill=ERROR)
    hint, hint_font = _fit(draw, "see the log", max(1, size[0] - 16), 13)
    draw.text((8, 30), hint, font=hint_font, fill=MUTED)
    return image


def compose(
    tiles: Sequence[Tile],
    size: tuple[int, int],
    *,
    sessions: Sequence[SessionState | None] = (),
    now: datetime,
    background: Background | None = None,
    connected: bool = True,
    idle_title: str = "",
    messages: MessageSnapshot | None = None,
    notifications: NotificationSnapshot | None = None,
    todos: TodoSnapshot | None = None,
) -> Image.Image:
    """Render every tile and composite them into one frame.

    `sessions` supplies one entry per session-wanting tile, in tile order; slots
    are numbered here rather than in config so the user never hand-numbers them.
    """
    from .widgets import WIDGETS

    full_screen = (
        len(tiles) == 1
        and tiles[0].origin == (0, 0)
        and tiles[0].size == size
    )
    slot = -1
    frame: Image.Image | None = None

    for tile in tiles:
        spec = WIDGETS[tile.widget]
        session = None
        if spec.wants_session:
            slot += 1
            session = sessions[slot] if slot < len(sessions) else None
        context = TileContext(
            size=tile.size,
            now=now,
            options=tile.options,
            session=session,
            slot=slot if spec.wants_session else -1,
            connected=connected,
            idle_title=idle_title,
            messages=messages if spec.wants_messages else None,
            notifications=notifications if spec.wants_notifications else None,
            todos=todos if spec.wants_todos else None,
        )
        try:
            drawn = spec.render(context)
        except Exception:
            LOG.exception("Widget %r failed; painting a fault tile", tile.widget)
            drawn = _fault_tile(tile.size, tile.widget)
        if drawn.size != tile.size:
            LOG.warning(
                "Widget %r returned %sx%s for a %sx%s tile; cropping",
                tile.widget,
                *drawn.size,
                *tile.size,
            )
            drawn = drawn.crop((0, 0, tile.w, tile.h))

        # A single full-screen opaque tile is the legacy 480x320 panel. Handing
        # its image straight back — no base layer, no paste — is what makes that
        # path byte-identical to calling render_dashboard directly.
        if full_screen and drawn.mode == "RGB":
            return drawn
        if frame is None:
            frame = background_layer(background or Background(), size)
        frame.paste(drawn, tile.origin, drawn if drawn.mode == "RGBA" else None)

    if frame is None:
        frame = background_layer(background or Background(), size)
    return frame if frame.mode == "RGB" else frame.convert("RGB")
