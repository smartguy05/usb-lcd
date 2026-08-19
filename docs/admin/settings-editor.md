# The settings editor

> **Covers:** `src/usb_lcd_dashboard/admin.py`, `src/usb_lcd_dashboard/admin_page.py`

A drag-a-rectangle layout editor served on `127.0.0.1:45723` from inside the
daemon. It runs inside the daemon rather than as a separate tool because it
shows a live view of the frame **actually on the panel**, which only the daemon
has.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `AdminState` | `admin.py:243` | The daemon's side: config path, `get_config`, `get_preview`. |
| `AdminState.save(payload)` | `admin.py:278` | Validate and write. Raises `ValueError`. |
| `make_handler(state)` | `admin.py:360` | Builds the request handler. |
| `start(state, port)` | `admin.py:676` | A `ThreadingHTTPServer`, returned to the daemon. |
| `config_to_json(cfg)` / `config_from_json(data)` | `:63` / `:124` | The wire shape. |
| `PAGE` | `admin_page.py` | The whole UI as one self-contained string. |

## Routes

All guarded by `_guard()` first.

| Method | Route | Response |
| --- | --- | --- |
| GET | `/`, `/index.html` | `200` the page (`text/html`). |
| GET | `/api/config` | `200` `config_to_json(...)`. |
| GET | `/api/widgets` | `200` `{"widgets": describe()}`. |
| GET | `/api/preview.png` | `200` PNG, or **`503`** if no frame has been rendered yet. |
| GET | `/api/todos?include_completed=1` | Open todos, optionally with completed history. |
| POST | `/api/todos`, `/api/todos/reorder`, `.../complete`, `.../reopen` | Create, order, or change status. |
| PATCH / DELETE | `/api/todos/{id}` | Edit, or permanently delete with `{"confirm":true}`. |
| POST | `/api/config` | `200` the saved config, `400` bad JSON or invalid config, `413` oversized body. |
| POST | `/api/layout/rotate` | Rotate the canvas and every tile between mounting orientations. |
| POST | `/api/background-image` | Validate and stage a managed PNG/JPEG/WebP wallpaper. |
| any | anything else | `404`. |
| any | non-loopback `Host` | `403`. |

`GET /api/preview.png` is the most useful route for an agent: it returns the
exact frame on the panel right now, with no hardware needed.

```bash
curl -s -o frame.png http://127.0.0.1:45723/api/preview.png
```

## The shape of the page

Three stacked regions, in this order:

1. **The stage** — the drag-a-rectangle canvas, always visible, because
   everything else on the page is relative to a tile on it. `drawStage`
   (`admin_page.py:525`) sizes it from explicit `cfg` pixels rather than from a
   measured container, so it does not care what is hidden below it.
2. **Settings** — a collapsed `<details>` holding Background, Screen saver and
   Display: the settings that belong to the whole screen rather than to a tile.
   `<details>` does the collapsing; there is no JS state behind it.
3. **A tabstrip** — *Live panel* (the frame currently on the panel) and *Widget
   settings* (everything about the selected tile).

Selecting a tile, or adding one, switches to the widget tab: picking a tile is
the way into its settings. The live preview stops polling `/api/preview.png`
while its tab is hidden or the browser tab is in the background, and re-arms on
the way back (`refreshPreview`, `admin_page.py:1069`).

### Source-backed blocks follow their widget

Discord, Windows notifications and human todos each configure a *source* that
exactly one widget consumes, so they live in the widget tab and are shown only
while a widget that consumes them is selected. `showContextSections`
(`admin_page.py:710`) reads the `wants_*` flags straight off `/api/widgets`:

| Registry flag | Block shown |
| --- | --- |
| `wants_session` | Dashboard — idle title, switch dwell, the three TTLs |
| `wants_messages` | Discord messages |
| `wants_notifications` | Windows notifications |
| `wants_todos` | Human todos |

There is no list of widget names anywhere in that mapping, so a new
source-backed widget wires itself up by declaring the flag.

Every one of those blocks stays in the DOM at all times and is toggled with
`hidden`, never created or destroyed. Listeners are bound at parse time, the
5-second `refreshDiscord`/`refreshTodos` polls write into their mounts
regardless of what is on screen, and `drawTodoCreate` clears `#todoCreate`
without a null guard — removing a mount would break all three.

## Security model

Two independent defences, both deliberate:

1. **Bound to loopback only.** `ADMIN_HOST` is a hardcoded constant in
   [config.py](../runtime/config.md) and is not configurable. The editor
   rewrites `config.toml` and has no authentication.
2. **The `Host` header must be loopback** (`_host_is_loopback`, `admin.py:47-60`;
   enforced by `_guard`, `:381-385`). This is the DNS-rebinding defence: a
   malicious page cannot make a browser POST a new config by resolving a
   hostname to 127.0.0.1, because the `Host` header would carry that hostname.

An oversized POST body is drained before the `413` is sent (`:594-607`) —
otherwise the reply races the request and the client sees a connection reset
instead of the status. Beyond a drain cap, the connection is closed rather than
reading an unbounded body.

## Saving

`AdminState.save` (`admin.py:278-288`) round-trips the candidate through
`parse_config_text(dump_config_toml(candidate))` — **the same loader the daemon
uses**. The editor therefore cannot accept a config the daemon would then refuse
to start on, and there is no second copy of the validation rules. A rejection
names the offending field or tile and writes nothing.

The write itself is `write_config`, which replaces the file atomically.

Wallpaper uploads are decoded with Pillow, limited to 10 MiB and 25 megapixels,
EXIF-oriented, stripped to RGB PNG, and stored under a content-derived name in
`backgrounds/` beside the config. Uploading does not activate the file; Save
does, while Revert leaves the current config untouched. A later successful save
prunes superseded files only from that managed directory.

Todo actions are deliberately separate from config saving. They commit
immediately through `TodoStore`, so Save/Revert for layout edits cannot discard
or overwrite the human list. Completed items are hidden from the LCD but remain
available in the editor for reopening or confirmed deletion.

## How the daemon notices

There is no shared state between the editor thread and the loop. **The file is
the only channel.** The daemon compares the config file's raw bytes once a
second and reloads on a change — see
[../runtime/daemon.md](../runtime/daemon.md#config-hot-reload) for why it hashes
contents rather than checking mtime.

Two consequences worth knowing: saving **rewrites `config.toml` in canonical
form**, dropping hand-written comments; and `[ipc]`/`[admin]` are shown but not
editable, because changing the IPC transport would orphan the installed hooks
and changing the editor's port would cut off the page you are using.

## The form builds itself

`admin_page.py` contains no widget knowledge at all. It fetches
`/api/widgets` and generates inputs from the `Option` types the registry
declares. Register a widget and it appears in the editor with working inputs and
its own help text, with no change here — see
[../rendering/widgets.md](../rendering/widgets.md#adding-a-widget).

`field()` (`admin_page.py:609`) maps each declared type to a control: `bool` to
a checkbox, `number` to a spinner, `text` to a text box, and `color` to a
colour chip beside a text box. **The text box stays the value of record for a
colour**, because `"transparent"` and `""` (meaning "fall back to the widget
default") are both legal and neither can be spelled by `<input type=color>`; the
chip greys out for a named colour and shows a chequerboard for none.

Two presentation-only lookups sit above the registry rather than in it, so that
`Option` keeps its three fields and the tests that pin the `/api/widgets` shape
keep passing:

- `LABELS` (`:272`) turns `show_project` into "Show the project" and overrides
  the handful that do not humanise well (`hour12` → "12-hour clock").
- `RANGES` (`:295`) puts `min`/`max`/`step` on the inputs, mirroring limits the
  loader already enforces. The loader stays the enforcer; these only make the
  spinner behave and let the browser flag a bad value before Save does.

### Switching back to the legacy LCD

Choosing `turing_rev_a` or `auto` in the display-kind picker restores the
orientation-correct legacy canvas (`480×320` landscape or `320×480` portrait)
and replaces the current layout with one full-screen `legacy` tile. This prevents
a wide-panel layout from being sent to the fixed-size Rev A serial display. Other
display kinds retain their editable dimensions and tiles.

## Tests

`tests/test_admin.py` — every route and status code, the loopback guard, the
save round-trip rejecting each loader rule, and the preview lifecycle. It also
pins the page's structure: that the stage sits outside the tabs, that every
source-backed section exists in the DOM but starts hidden, and that the preview
poll is gated.

## See also

- [tray.md](tray.md) — the other optional sub-service.
- [../runtime/config.md](../runtime/config.md) — the loader it shares.
- [../runtime/daemon.md](../runtime/daemon.md) — who starts it.
