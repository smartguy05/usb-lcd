# config.py — the single source of config truth

> **Covers:** `src/usb_lcd_dashboard/config.py`

Owns the `Config` dataclass, TOML load/parse/dump/write, and path resolution.
Every default lives here exactly once; the example TOML files are *generated*
from it and a test asserts they have not drifted.

When `display.kind = "auto"`, `profiles.py` stores one complete configuration
per detected panel under the sibling `profiles/` directory. `config.toml`
remains the active copy, so hand edits and the settings editor work unchanged.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `Config` | `config.py:55` | Frozen, slotted dataclass. Every tunable. |
| `.size` / `.socket_path` / `.ipc_address` / `.frame_interval` | `:96`-`:111` | Derived properties. |
| `config_home()` | `:40` | `%LOCALAPPDATA%` or `$XDG_CONFIG_HOME`/`~/.config`. |
| `runtime_dir()` | `:48` | Where the Unix socket lives. |
| `default_path()` | `:284` | `$USB_LCD_DASHBOARD_CONFIG` override, else `config_home()/usb-lcd-dashboard/config.toml`. |
| `load_config(path=None, *, strict=True)` | `:355` | Read and parse, or return defaults. |
| `parse_config(data, *, strict=True)` | `:387` | Validate a loaded dict. |
| `parse_config_text(text)` | `:378` | Validate a TOML string — the editor's gate. |
| `dump_config_toml(cfg)` | `:206` | Serialise back to TOML. |
| `default_config_toml(device=None, ipc_mode=None)` | `:147` | The starter config, rendered from `Config()`. |
| `write_config(cfg, path=None)` | `:269` | Atomic replace. |

## Selected fields

Full list at `config.py:55-94`. The ones that bite:

| Field | Default | Note |
| --- | --- | --- |
| `device` | `AUTO` (Win) / `/dev/turing-lcd` | The POSIX path is created by the udev rule. |
| `display_kind` | `turing_rev_a` | Must be in `DISPLAY_KINDS`. |
| `refresh_hz` | `2.0` | Clamped to `[0.25, 10]` by `frame_interval`. |
| `brightness` | `25` | **Range is 0–50, not 0–100.** |
| `tiles` | `()` | Empty means the legacy full-screen tile, synthesised at load. |
| `tool_ttl_seconds` | `900` | A tool call emits nothing until it returns. |
| `switch_dwell_seconds` | `4.0` | Keeps a chatty session from stealing every frame. |
| `ipc_mode` | `tcp` (Win) / `unix` | |
| `admin_port` | `45723` | Must differ from `ipc_port` (`:437-438`). |
| `layout_error` | `""` | Set only by a lenient load; always empty on a strict one. |
| `orientation` | `landscape` | Four mounting rotations; portrait canvases swap width/height. |
| `screensaver_enabled` / `screensaver_idle_seconds` | `true` / `600` | Moving-clock idle protection. |

Constants: `DEFAULT_IPC_PORT = 45722`, `DEFAULT_ADMIN_PORT = 45723`,
`ADMIN_HOST = "127.0.0.1"`, `DISPLAY_KINDS`, `NO_WINDOW`, `DEVICE_BY_ID`.

`ADMIN_HOST` is hardcoded loopback and deliberately not configurable
(`config.py:23-26`): the editor rewrites config.toml and has no authentication,
so *"binding it anywhere routable would hand the panel's configuration to the
network."*

## Strict vs lenient loading

The single most important rule in this file. From `load_config`
(`config.py:356-364`):

> `strict=False` is for the commands that need nothing but the IPC address and
> the paths — the hooks, and install/uninstall. A tile rect is a display
> setting, and letting one fail those commands means a single bad widget name
> makes *every* hook in *every* Claude and Codex session dump a traceback, and
> blocks the very command that would repair the file.

- **Strict** (`run` only): a bad layout raises.
- **Lenient** (everything else): the layout is logged, replaced with the default
  full-screen tile, and the reason is recorded in `Config.layout_error` so
  [`doctor`](../integration/cli.md#doctor) can report it instead of crashing.
- **Everything outside the layout is validated either way** — a wrong
  `ipc.port` would silently send events nowhere, which is worse than a crash.

Implemented by `_with_layout(cfg, strict=...)` (`:334-352`). Dispatched in
[cli.py](../integration/cli.md) by command name.

## Adding a setting

Four places, and a test will fail if you miss one:

1. A field on `Config` (`:55`).
2. Parsing in `parse_config` (`:387`).
3. Serialising in `dump_config_toml` (`:206`) — tomllib reads but cannot write.
4. The template `DEFAULT_CONFIG_TOML` plus its `.format()` call in
   `default_config_toml` (`:155`).

`default_config_toml` is generated from `Config()` precisely so this cannot
drift (`:148-153`): it used to be four hand-maintained copies.
`tests/test_config.py::test_example_configs_have_not_drifted_from_the_defaults`
is the gate.

## Other gotchas

- `_toml_value` checks `bool` before `int` (`:185-189`) because `bool` *is* an
  `int` in Python and would otherwise serialise as `1`/`0`.
- Paths dump as forward slashes even on Windows (`:192-195`) — still valid, far
  easier to hand-edit.
- `write_config` writes a sibling `.tmp` then `os.replace`s it (`:269-281`),
  because the daemon watches this file and must never read a half-written one.
- A background image that does not exist warns but loads (`:301-304`) — a config
  synced between two machines may name a wallpaper only one of them has.

## Tests

`tests/test_config.py` — example drift, round-tripping through dump/load,
atomic write, admin block parsing, port validation, and the whole strict/lenient
matrix.

## See also

- [../architecture/invariants.md](../architecture/invariants.md)
- [../integration/cli.md](../integration/cli.md) — who loads strictly.
- [../admin/settings-editor.md](../admin/settings-editor.md) — the other writer.
- [../reference/config-schema.md](../reference/config-schema.md) — every key, as TOML.
