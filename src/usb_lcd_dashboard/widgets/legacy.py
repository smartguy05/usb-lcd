"""The 3.5" panel's existing layout, as a single full-screen widget.

render_dashboard and render_idle are untouched and still produce every pixel.
Routing them through the tile composer instead of forking the daemon loop means
there is one place slots are assigned and one place faults are handled, and the
composer's full-screen fast path hands this image straight back to the display —
so the frame is the identical object, not a copy of one.
"""

from __future__ import annotations

from PIL import Image

from ..layout import TileContext
from ..render import render_dashboard, render_idle


def render_legacy(ctx: TileContext) -> Image.Image:
    if ctx.session is not None:
        return render_dashboard(ctx.session, ctx.now)
    return render_idle(
        ctx.options.get("title") or ctx.idle_title, ctx.now, ctx.connected
    )
