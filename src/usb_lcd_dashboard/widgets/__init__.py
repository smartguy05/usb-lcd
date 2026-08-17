"""Widgets: plain functions that render one tile.

A widget takes a TileContext and returns an image of the tile's exact size. That
is the same shape render_dashboard and render_idle already had — they were
full-screen widgets all along — and it means widget code counts from (0, 0)
instead of threading a rect offset through every draw call. It also clips a
widget to its own tile and lets the compositor isolate a fault to one rectangle.

Widgets return RGBA so a tile can be translucent over a background image.

Each widget also declares its options, so the settings editor can build a form
for it without knowing anything about the widget, and a new widget shows up there
with working inputs the moment it is registered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from PIL import Image

from ..layout import TileContext
from .agent import render_agent
from .clock import render_clock
from .crab import render_crab
from .legacy import render_legacy
from .messages import render_messages

Renderer = Callable[[TileContext], Image.Image]

OPTION_TYPES = ("bool", "text", "number", "color")


@dataclass(frozen=True, slots=True)
class Option:
    type: str
    default: Any = None
    help: str = ""


# Every tile drawn with widgets.base.new_tile honours these.
COMMON_OPTIONS: dict[str, Option] = {
    "background": Option(
        "color", "#101c28", 'Card colour, or "transparent" for none'
    ),
    "opacity": Option("number", 1.0, "0 to 1; lets a background image read through"),
}


@dataclass(frozen=True, slots=True)
class WidgetSpec:
    render: Renderer
    # The only cross-tile resource in play. Everything else a widget needs it
    # fetches itself from its own options, so this stays a bool, not a DSL.
    wants_session: bool = False
    wants_messages: bool = False
    options: dict[str, Option] = field(default_factory=dict)
    help: str = ""


WIDGETS: dict[str, WidgetSpec] = {
    "agent": WidgetSpec(
        render_agent,
        wants_session=True,
        options=dict(COMMON_OPTIONS),
        help="A Claude Code or Codex session. The number of these caps how many "
        "sessions show at once.",
    ),
    "crab": WidgetSpec(
        render_crab,
        wants_session=True,
        options={
            "color": Option("color", "", "Crab colour; blank follows the provider"),
            "animate": Option("bool", True, "Move. Off draws one still pose"),
            "show_project": Option("bool", True, "Project name and branch"),
            "show_activity": Option("bool", True, "What the agent is doing now"),
            "show_context": Option("bool", True, "Context-used bar along the bottom"),
            "alarm": Option("bool", True, "Pulse the border when an approval waits"),
            **COMMON_OPTIONS,
        },
        help="A session as an animated crab that reacts to what the agent is "
        "doing, and waves both claws when it needs you. Like the agent card, "
        "each of these takes a session slot.",
    ),
    "clock": WidgetSpec(
        render_clock,
        options={
            "title": Option("text", "", "Small label in the corner"),
            "hour12": Option("bool", True, "12-hour rather than 24-hour"),
            "seconds": Option("bool", False, "Show seconds beside the time"),
            "show_date": Option("bool", True, "Show the weekday and date"),
            **COMMON_OPTIONS,
        },
        help="The time, with an optional date line.",
    ),
    "legacy": WidgetSpec(
        render_legacy,
        wants_session=True,
        options={"title": Option("text", "", "Overrides dashboard.idle_title")},
        help="The 3.5\" panel's original full-screen card. Meant to be the only "
        "tile, covering the whole display.",
    ),
    "messages": WidgetSpec(
        render_messages,
        wants_messages=True,
        options={
            "title": Option("text", "Teams", "Heading shown above the latest unread chat"),
            **COMMON_OPTIONS,
        },
        help="The newest unread Microsoft Teams chat and the number of unread chats.",
    ),
}


def describe() -> list[dict[str, Any]]:
    """The registry as JSON for the settings editor."""
    return [
        {
            "name": name,
            "wants_session": spec.wants_session,
            "wants_messages": spec.wants_messages,
            "help": spec.help,
            "options": [
                {
                    "name": option,
                    "type": meta.type,
                    "default": meta.default,
                    "help": meta.help,
                }
                for option, meta in spec.options.items()
            ],
        }
        for name, spec in sorted(WIDGETS.items())
    ]
