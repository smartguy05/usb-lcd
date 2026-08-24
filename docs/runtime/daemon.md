# daemon.py — the process and its loop

> **Covers:** `src/usb_lcd_dashboard/daemon.py`

Owns the process lifecycle: the loop that receives an IPC event, updates session
state, composes a frame and paints it, plus config hot-reload and the optional
admin and tray sub-services.

It deliberately owns none of the meaning. Event parsing is
[normalize.py](../sessions/normalize.md), session bookkeeping is
[model.py](../sessions/model.md), layout maths is
[layout.py](../rendering/layout.md), and panel I/O is
[display.py](display.md) / [transport.py](transport.md). The daemon only
orchestrates them.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `DashboardDaemon` | `daemon.py:19` | The whole daemon. |
| `.__init__(config, simulate=False, config_path=None)` | `daemon.py:20` | Builds display, store, slot count, config baseline. |
| `.run()` | `daemon.py:147` | Signal handlers, bind, start sub-services, loop until stopped. |
| `.stop(*_args)` | `daemon.py:133` | Sets `running = False`. Used directly as the SIGINT/SIGTERM handler *and* as the tray's quit callback. |

Internal but load-bearing: `_apply_config` (`:36`), `_config_signature` (`:51`),
`_reload_config` (`:64`), `_start_admin` (`:103`), `_start_tray` (`:121`),
`_connect` (`:136`).

## Instance state

Set in `__init__` (`daemon.py:20-34`):

| Attribute | Meaning |
| --- | --- |
| `display` | A [`Display`](display.md), built whether or not hardware exists. |
| `profiles` | Hardware-keyed configurations used while `display.kind` is `auto`. |
| `store` | The [`StateStore`](../sessions/model.md). |
| `slot_count` | How many sessions can be on screen — derived *from the layout*, not configured. |
| `running` | Loop flag. |
| `next_connect` | Monotonic gate for reconnect backoff. |
| `last_loop_tick` | Detects a suspend/resume-sized pause so the stale display handle can be replaced. |
| `config_signature` | Raw bytes of config.toml, for change detection. |
| `next_config_check` | Monotonic gate throttling reload checks to 1 Hz. |
| `last_frame` | Last composed image, for the editor's preview. |
| `last_activity` | Monotonic timestamp used by the screen-saver deadline. |
| `admin`, `tray` | Optional sub-services, `None` until started. |

## The loop, step by step

`run()` at `daemon.py:147-229`:

1. `:148` Install `stop` as the SIGINT/SIGTERM handler.
2. `:150` `bind_socket(config)` — Unix datagram or TCP listener per `ipc_mode`.
3. `:151-152` Start the [editor](../admin/settings-editor.md) and
   [tray](../admin/tray.md). Both best-effort; see *Failure* below.
4. Loop while `running` (`:154`):
   - `:155` `_connect()` — open the panel if disconnected and past the backoff.
   - `:156-157` Push connection state to the tray.
   - `:158` `_reload_config()` — throttled config check.
   - `:159-181` Receive and apply **one** event. A `{"control": "shutdown"}`
     envelope stops the loop and `continue`s, skipping a final frame. A
     `schema_version: 1` envelope goes through `normalize_event` into the store.
   - `:183-184` `store.assign(slot_count, now)` decides who gets screen time.
   - The moving-clock screen saver replaces composition after the configured
     inactivity delay; accepted events or changed visible content wake it.
   - `compose(...)` otherwise builds the frame, wrapped in a backstop except.
   - `:202-205` Keep `last_frame` regardless of connection state.
   - `:206-212` `display.paint(frame)` if connected; on failure close and back
     off 2 s.
   - `:213-219` Recompute `poll_timeout`, re-apply it to the socket, and sleep
     only the remainder of the frame.
5. `finally` (`:220-229`) Close the socket, unlink the Unix socket, shut down
   admin and tray, close the display. Always runs.

### One event per tick

The loop reads at most one event per iteration, so a burst drains at the frame
rate rather than all at once. At 8 Hz that is 8 events/second. This is why a
rapid sequence of hook events appears on the panel slightly behind the terminal.

## Config hot-reload

`_reload_config()` (`daemon.py:64-101`):

1. Bail unless 1 s has passed (`:73-74`).
2. Read the file's **bytes** as the signature (`:77-78`).
3. Store the new signature *before* attempting to load (`:79`), so a config that
   will not load is not retried every tick.
4. `load_config(path)` — strict. On any exception, warn and keep the last good
   one (`:80-84`).
5. Compare size/kind/device/orientation/brightness to decide `display_changed`.
6. `_apply_config(fresh)` swaps config, updates store TTLs, recomputes
   `slot_count`, updates the tray.
7. If the display settings changed, rebuild `Display` and force a reconnect.

## Sleep/resume recovery

If consecutive loop ticks are separated by ten seconds or more, the daemon
treats the gap as suspend/resume (or a stalled USB stack), closes the old display
handle, and reconnects before painting again. A `reconnect` control envelope
provides the same recovery path when the Start-menu shortcut is launched while
the daemon is already running.

**Contents, not mtime** — quoted from `_config_signature` (`daemon.py:51-58`):

> Not the mtime: a save can land inside the same filesystem timestamp tick as
> the write before it, and the edit would then be silently ignored until
> something else touched the file — which from the editor looks like Save doing
> nothing.

`tests/test_daemon.py::test_a_save_in_the_same_timestamp_tick_is_still_noticed`
pins exactly that.

**The file is the only channel** between the editor thread and the loop
(`daemon.py:67-71`), which is why there is no shared mutable state between them.

## Invariants

- **The `compose()` except is a backstop, not the fault isolation.**
  `daemon.py:196-199`: compose already isolates a widget's fault to its own
  tile; this catches a fault in composition itself, *"which would otherwise
  strand the panel on its last frame with nothing to say why."*
- **`last_frame` updates even when disconnected** (`:203-204`) so the editor
  preview works before the hardware arrives.
- **The sleep only makes up the remainder of the frame.** The receive already
  blocked for up to `poll_timeout`. Both come from the live config, so an edited
  `refresh_hz` applies on the next iteration without a restart. See
  [transport.md](transport.md#poll_timeout-is-the-real-frame-rate-floor).
- **Sub-services never take the panel down.** *"The editor is a convenience; the
  panel is the job"* (`:117-119`); *"a daemon with no icon is still a working
  daemon"* (`:128-131`).
- **`_apply_config` guards with `getattr(self, "tray", None)`** (`:45-46`)
  because it runs once during `__init__`, before `tray` exists.
- Two distinct backoffs on purpose: 3 s after a failed connect (`:145`), 2 s
  after a failed write (`:212`).

## Failure modes

| Failure | Result |
| --- | --- |
| Malformed IPC data | Warning, event dropped, loop continues (`:180-181`). |
| `compose()` raises | `LOG.exception`, frame skipped, previous frame stays up (`:195-201`). |
| Connect fails | Warning, display closed, retry in 3 s (`:142-145`). |
| Write fails | Warning, display closed, retry in 2 s. Next connect repaints fully. |
| Config will not load | Warning, last good config kept, not retried until the file changes again. |
| Admin or tray will not start | Warning, feature absent, daemon runs. |

## Tests

`tests/test_daemon.py` pins slot count derivation, TTLs from config, live
layout/timing reload, the same-tick save, invalid-config tolerance, reload
throttling, reconnect-on-resize vs no-reconnect-on-layout-change, editor
enable/disable/port-in-use, and tray start/failure/quit/config propagation.

## See also

- [transport.md](transport.md) — the socket and the poll timeout it sets.
- [display.md](display.md) — what `paint()` does with the frame.
- [config.md](config.md) — `Config`, strict vs lenient loading.
- [../architecture/overview.md](../architecture/overview.md) — the whole path.
- [../architecture/invariants.md](../architecture/invariants.md) — repo-wide rules.
