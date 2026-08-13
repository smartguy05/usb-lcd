# model.py — session state and tile arbitration

> **Covers:** `src/usb_lcd_dashboard/model.py`

`SessionState` is one session's known state. `StateStore` merges updates and
decides which live sessions get screen time. `assign()` is the subtlest code in
the repository; `tests/test_state.py` pins every rule below.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `utc_now()` | `model.py:9` | The single time source, injectable in tests. |
| `SessionState` | `model.py:13` | One session. `slots=True` dataclass. |
| `.project` | `model.py:32` | `Path(cwd).name`, else `"unknown project"`. |
| `StateStore(active_ttl=180, approval_ttl=90, tool_ttl=900, switch_dwell=4.0)` | `model.py:41` | |
| `.apply(update) -> SessionState` | `model.py:61` | Merge an incoming update. |
| `.assign(slots, now=None) -> list[SessionState \| None]` | `model.py:117` | The arbiter. |
| `.active(now=None)` | `model.py:113` | Literally `assign(1)[0]`. |

Sessions are keyed by `(provider, session_id)`.

For every `SessionState` field and which payload key fills it, see
[normalize.md](normalize.md).

## Store attributes

| Attribute | Meaning |
| --- | --- |
| `sessions` | Everything known, by key. |
| `shown` | What each session's `updated_at` was when it was last on screen. This is the freshness watermark. |
| `slots` | One entry per session-capable tile. The 3.5" panel is the one-slot case. |
| `since` | When each slot was last filled, for dwell. |

## `apply()` — merge rules

`model.py:61-95`.

- **Most optional fields carry forward when absent.** `detail`, `model`, `cwd`,
  `permission_mode`, `context_percent`, `input_tokens`, `output_tokens`,
  `cost_usd`: an incoming `""`/`None` keeps the previous value, so a sparse
  event does not blank what is already known.
- **`activity` deliberately does not** (`model.py:75-76`): *"a prompt or stop
  event carries no tool, and its empty activity must clear the stale one."*
- **`started_at` survives** because it is excluded from the replaced fields, so
  `replace()` keeps the original even though `normalize_event` sets it on every
  call. Only the first event for a session establishes it.
- **`extra` merges** rather than replacing.
- **The `StatusLine` special case** (`:65-69`): a status-line refresh carries
  model, context and cost but no phase, so `phase`, `detail`, `activity` and
  `ended` are overwritten from the *previous* state before merging. Without it,
  every status-line tick would reset a session's phase and blank its activity.

## `assign()` — the arbiter

`model.py:117-248`, in execution order.

1. **Liveness** (`:132-138`). Keep sessions that are not `ended` and whose age is
   within their TTL. `_ttl` (`:97`) returns `tool_ttl` (900 s) for phase `TOOL`,
   else `active_ttl` (180 s) — *"A session waiting on a tool has work in flight
   and emits nothing until the tool returns."* Without this, real work times out
   and vanishes.
2. **Prune `shown`** (`:139-140`) of anything no longer live, so a session that
   comes back is treated as new.
3. **Resize** slots to the tile count (`:141`).
4. **Clear stale and duplicate slots** (`:158-168`) so a session can never
   occupy two tiles.
5. **Build the queues.** `approvals` — phase `APPROVAL` within `approval_ttl`,
   newest first. `fresh` — not already placed, and `updated_at` differs from
   `shown`, i.e. it has something new. Newest first.
6. **Fill empty tiles with no dwell wait** (`:191-201`), in the order approvals,
   fresh, then *any* live session. *"An empty tile displaces nothing"*, and the
   third group stops a tile sitting blank while a quiet-but-live session exists.
7. **Approvals preempt** (`:203-227`), ignoring the dwell floor. They evict the
   tile that has been sitting **longest**, not tile zero: *"so it displaces the
   least recently interesting session instead of one that just arrived."*
8. **Everything else waits for dwell** (`:229-243`). A fresh session can only
   evict a tile held for at least `switch_dwell` seconds. Without that floor, a
   session emitting an event a second takes every frame and quieter sessions are
   never on screen long enough to read.
9. **Record and return** (`:245-248`): update `shown` for everything on screen.

Two rules hold throughout:

- **A placed session is never relocated, only evicted** — nothing hops between
  tiles from frame to frame.
- **Tiles filled during this call are off limits to later steps** (`placed`,
  `:181`), or a dwell of zero would let each candidate evict the previous one
  and the least interesting session would end up on screen.

`assign()` **mutates** `slots`, `since` and `shown`. It is not a pure query.

## See also

- [normalize.md](normalize.md) — where `SessionState` comes from.
- [../rendering/layout.md](../rendering/layout.md) — `agent_slots` decides the slot count.
- [../reference/phases.md](../reference/phases.md) — the phase strings.
- `tests/test_state.py` — the executable specification.
