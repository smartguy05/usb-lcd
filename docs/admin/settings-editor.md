# The settings editor

> **Covers:** `src/usb_lcd_dashboard/admin.py`, `src/usb_lcd_dashboard/admin_page.py`

A drag-a-rectangle layout editor served on `127.0.0.1:45723` from inside the
daemon. It runs inside the daemon rather than as a separate tool because it
shows a live view of the frame **actually on the panel**, which only the daemon
has.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `AdminState` | `admin.py:194` | The daemon's side: config path, `get_config`, `get_preview`. |
| `AdminState.save(payload)` | `admin.py:207` | Validate and write. Raises `ValueError`. |
| `make_handler(state)` | `admin.py:217` | Builds the request handler. |
| `start(state, port)` | `admin.py:314` | A `ThreadingHTTPServer`, returned to the daemon. |
| `config_to_json(cfg)` / `config_from_json(data)` | `:57` / `:106` | The wire shape. |
| `PAGE` | `admin_page.py` | The whole UI as one self-contained string. |

## Routes

All guarded by `_guard()` first.

| Method | Route | Response |
| --- | --- | --- |
| GET | `/`, `/index.html` | `200` the page (`text/html`). |
| GET | `/api/config` | `200` `config_to_json(...)`. |
| GET | `/api/widgets` | `200` `{"widgets": describe()}`. |
| GET | `/api/preview.png` | `200` PNG, or **`503`** if no frame has been rendered yet. |
| POST | `/api/config` | `200` the saved config, `400` bad JSON or invalid config, `413` oversized body. |
| any | anything else | `404`. |
| any | non-loopback `Host` | `403`. |

`GET /api/preview.png` is the most useful route for an agent: it returns the
exact frame on the panel right now, with no hardware needed.

```bash
curl -s -o frame.png http://127.0.0.1:45723/api/preview.png
```

## Security model

Two independent defences, both deliberate:

1. **Bound to loopback only.** `ADMIN_HOST` is a hardcoded constant in
   [config.py](../runtime/config.md) and is not configurable. The editor
   rewrites `config.toml` and has no authentication.
2. **The `Host` header must be loopback** (`_host_is_loopback`, `admin.py:41-54`;
   enforced by `_guard`, `:238-242`). This is the DNS-rebinding defence: a
   malicious page cannot make a browser POST a new config by resolving a
   hostname to 127.0.0.1, because the `Host` header would carry that hostname.

An oversized POST body is drained before the `413` is sent (`:279-286`) —
otherwise the reply races the request and the client sees a connection reset
instead of the status. Beyond a drain cap, the connection is closed rather than
reading an unbounded body.

## Saving

`AdminState.save` (`admin.py:207-214`) round-trips the candidate through
`parse_config_text(dump_config_toml(candidate))` — **the same loader the daemon
uses**. The editor therefore cannot accept a config the daemon would then refuse
to start on, and there is no second copy of the validation rules. A rejection
names the offending field or tile and writes nothing.

The write itself is `write_config`, which replaces the file atomically.

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

## Tests

`tests/test_admin.py` — every route and status code, the loopback guard, the
save round-trip rejecting each loader rule, and the preview lifecycle.

## See also

- [tray.md](tray.md) — the other optional sub-service.
- [../runtime/config.md](../runtime/config.md) — the loader it shares.
- [../runtime/daemon.md](../runtime/daemon.md) — who starts it.
