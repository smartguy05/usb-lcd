# config.toml

Every key, with its default. Generated from the `Config` dataclass — see
[../runtime/config.md](../runtime/config.md) for the loader and for how to add a
setting.

Location: `$USB_LCD_DASHBOARD_CONFIG`, else
`%LOCALAPPDATA%\usb-lcd-dashboard\config.toml` on Windows or
`~/.config/usb-lcd-dashboard/config.toml` on Linux.

```toml
[display]
kind = "turing_rev_a"      # turing_rev_a | window | simulated | auto
device = "AUTO"            # or "/dev/turing-lcd" on Linux
width = 480
height = 320
orientation = "landscape"  # landscape | portrait
brightness = 25            # 0-50, NOT 0-100
refresh_hz = 2.0           # clamped to 0.25-10

[display.background]       # optional
color = "#081018"
# image = "C:/Users/you/Pictures/wallpaper.png"
fit = "cover"              # cover | contain | stretch | center

[dashboard]
active_ttl_seconds = 180
approval_ttl_seconds = 90
tool_ttl_seconds = 900     # a tool call emits nothing until it returns
switch_dwell_seconds = 4.0 # how long a session holds a tile
idle_title = "AI WORKBENCH"

[ipc]
mode = "tcp"               # tcp on Windows, unix on Linux
host = "127.0.0.1"
port = 45722

[admin]                    # the settings editor, loopback only
enabled = true
port = 45723               # must differ from ipc.port

[tray]                     # Windows only
enabled = true

[[tile]]                   # repeat per tile; omit entirely for the legacy layout
widget = "clock"           # clock | agent | crab | legacy
x = 12
y = 12
w = 404
h = 438
[tile.options]
# per-widget; see the table below
```

## Tile options

Every widget built on `new_tile` honours:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `background` | color | `#101c28` | The card, or `"transparent"` for none. |
| `opacity` | number | `1.0` | Lets a wallpaper read through. |

| Widget | Options |
| --- | --- |
| `agent` | the common two |
| `clock` | `title`, `hour12`, `seconds`, `show_date` |
| `crab` | `color`, `animate`, `show_project`, `show_activity`, `show_context`, `alarm` |
| `legacy` | `title` only — it paints its own opaque background |

The authoritative list is the registry itself; `GET /api/widgets` on the editor
returns it as JSON. See [../rendering/widgets.md](../rendering/widgets.md).

## Rules enforced at load

- Unknown widget names, overlapping tiles, non-positive sizes and off-panel
  rects are all rejected, naming the offending tile. A shared edge is not an
  overlap; gaps are fine.
- `admin.port` must differ from `ipc.port`.
- `brightness` 0–50; `width`/`height` 1–4096; ports 1024–65535.
- No `[[tile]]` at all means one full-screen `legacy` tile, so an existing
  install keeps working with no edits.

Only `run` treats a bad **layout** as fatal. Everything else substitutes the
default and records why — see
[../architecture/invariants.md](../architecture/invariants.md).

## Examples in the repo

`config.example.toml` (3.5" panel) and `config.example.wide.toml` (ultra-wide,
three tiles plus a crab). Both are asserted against the `Config` defaults by
`tests/test_config.py`, so they cannot drift.
