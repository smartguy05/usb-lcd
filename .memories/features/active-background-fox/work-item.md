# Active-background running fox

## Request
Add a widget: a cute, semi-realistic red fox that runs across the screen, exits
one edge, dwells, then re-enters from the other side. Running speed varies with
CPU usage. It renders **behind** the normal widgets as a live wallpaper ("active
background") and gets its **own tab** in the settings editor.

## Confirmed decisions
- Art: bundled sprite sheet (run-cycle PNG frames committed to repo).
- CPU source: add `psutil` runtime dependency (`cpu_percent`), cross-platform.
- Layer model: dedicated active-background slot in `Config` (NOT a z-index on
  `Tile`) — leaves tile overlap rules and the pixel-frozen legacy path untouched.
- Scope: background-only (not also a placeable foreground tile).

## Acceptance
- Fox runs left↔right, exits, dwells off-screen, re-enters from the other side.
- Speed scales with live CPU% between configurable min/max.
- Renders under all foreground tiles, over the wallpaper.
- Configurable + toggleable from a new "Active Background" tab in the editor.
- Full test suite green; installers rebuilt; docs + docs/ index updated.

## Key constraint
Tile widgets are pure functions of `ctx.now` (frozen TileContext, no state). A
CPU-varying speed needs position integrated over time → the active background is
STATEFUL and integrated in the daemon loop, distinct from stateless tiles. The
dedicated-slot model accommodates this (it is not a Tile).
