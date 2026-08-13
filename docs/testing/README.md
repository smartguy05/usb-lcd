# Testing

> **Covers:** `tests`

384 tests, one skipped on Windows, about 13 seconds. No linter or formatter is
configured. pytest config lives in `pyproject.toml` (`-q`,
`testpaths = ["tests"]`).

```bash
.venv/Scripts/pytest                                  # .venv/bin/pytest on Linux
.venv/Scripts/pytest tests/test_state.py -x
.venv/Scripts/pytest tests/test_crab.py::test_the_crab_blinks
.venv/Scripts/pytest --collect-only -q                # per-file counts
```

## Inventory

| File | Tests | Covers |
| --- | ---: | --- |
| `test_crab.py` | 84 | Pose model, blink schedule, alarm, size ladder. |
| `test_widgets.py` | 65 | Registry, and every widget at every size. |
| `test_admin.py` | 37 | Every editor route, the loopback guard, save validation. |
| `test_config.py` | 33 | Example drift, round-trips, strict/lenient loading. |
| `test_layout.py` | 25 | Validation, slots, compose, fault isolation. |
| `test_state.py` | 23 | `apply()` merge rules and the whole `assign()` arbiter. |
| `test_daemon.py` | 20 | Hot reload, sub-services, reconnect. |
| `test_activity.py` | 19 | Every tool's activity line. |
| `test_background.py` | 15 | Fit modes, caching, fallbacks. |
| `test_tray.py` | 13 | Tooltip, menu, icon states. |
| `test_device.py` | 9 | Kind-to-class mapping, guards, the window stub. |
| `test_display.py` | 9 | Dirty-rect diffing and the reopened-port contract. |
| `test_install.py` | 9 | Hook merging, the `Notification` hook, systemd wiring. |
| `test_normalize.py` | 8 | Payload to `SessionState`, both providers. |
| `test_transport.py` | 7 | Both transports, `poll_timeout`, the hook blast radius. |
| `test_legacy_identical.py` | 4 | The pixel-frozen contract. |
| `test_doctor.py` | 3 | Reporting a broken layout instead of raising. |
| `test_render.py` | 1 | The legacy card. |

## Shared idioms

Defined per-file rather than in a `conftest.py`:

| Helper | Where | Purpose |
| --- | --- | --- |
| `NOW` | most files | A fixed timestamp. Never `utc_now()` in a test. |
| `SIZES` | `test_widgets.py`, `test_crab.py` | A wide column, a square, the legacy panel, and two deliberately cramped strips nothing is tuned for. |
| `context(size, **kw)` | `test_widgets.py:21` | Build a `TileContext`. |
| `still(size, **kw)` | `test_crab.py` | Same, with `animate: False` — pins `t=0` so pixel tests are time-independent. |
| `full_session(**kw)` | both | A fully-populated `SessionState`. |
| `differs(a, b)` | both | See below. |
| `sweep(phase, seconds)` | `test_crab.py` | Poses across time, for asserting on motion without rendering. |

### `differs()` needs `alpha_only=False`

```python
ImageChops.difference(a, b).getbbox(alpha_only=False)
```

Pillow's `getbbox()` looks only at alpha by default, and these tiles are RGBA
with **identical** alpha — so a pure colour difference is invisible without the
flag. A test written without it silently passes no matter what changed.

## Patterns to follow

- **Widgets: assert on the pose, not the pixels.** The crab's motion is tested
  by sweeping simulated time and asserting properties — a blink occurs, nothing
  jumps between frames, the alarm swings wider than any calm phase — which is
  both faster and more meaningful than pinning a golden frame. Pixel tests use
  `animate: False`. See [../rendering/crab.md](../rendering/crab.md#testing-it).
- **Layout: inject fake widgets.** `test_layout.py` has an autouse fixture that
  adds test-only specs to `widgets.WIDGETS` and removes them on teardown, so
  composition is tested without depending on real widgets.
- **Config: exercise both strictness modes.** Every layout rule should be tested
  strict (raises) and lenient (falls back, records `layout_error`).
- **Pin the reason, not just the behaviour.** This suite writes the *why* into
  docstrings — several tests are explicit regression guards for a specific past
  bug, and say so. Keep that up; it is what makes a failure diagnosable.

## The pixel-frozen contract

`test_legacy_identical.py` renders the 480×320 card **both ways in one process**
— through `compose()` and through `render_dashboard()` directly — and asserts
the pixels are identical. It is not a golden file, so it keeps holding as the
layout system grows.

It breaks if you change the legacy card's drawing, or if you break any of the
three conditions for the fast path in
[../rendering/layout.md](../rendering/layout.md#the-legacy-fast-path). It is
also why `render.py` keeps its own copy of the context-bar drawing.

## Hazards

- **A live daemon may hold the IPC port.** 45722 on Windows, the Unix socket on
  POSIX. A test daemon started without a spare port will either fail to bind or
  feed the user's real panel. Every test binds an ephemeral port instead; do the
  same, or set `USB_LCD_DASHBOARD_CONFIG` to a config with distinct `ipc.port`
  and `admin.port`.
- **Two tests read files off the real repo, not `tmp_path`.**
  `test_config.py::test_example_configs_have_not_drifted_from_the_defaults` and
  its sibling read `config.example.toml` and
  `packaging/windows/config.example.toml` from disk. That is the point — they
  are the drift guard — but it means editing a `Config` default breaks them
  until the examples are regenerated.
- **Only `test_transport.py` monkeypatches `default_path`.** Its `_with_config`
  helper is the pattern to copy if you need a test to see a specific config;
  other suites pass a path explicitly.
- **One test is Windows-conditional**:
  `test_tray.py::test_no_tray_where_there_is_no_tray` is skipped on `nt`.
- **Historic trap**: an older `test_transport.py` test loaded the developer's
  *real* config and failed if it named a widget that commit predated. The
  lenient-loading fix removed the sting, but be wary of tests that call
  `load_config()` with no argument.

## See also

- [../architecture/invariants.md](../architecture/invariants.md) — the rules the suite enforces.
- [../index/README.md](../index/README.md) — find which test covers a symbol.
