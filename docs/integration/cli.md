# cli.py — every entry point

> **Covers:** `src/usb_lcd_dashboard/cli.py`, `src/usb_lcd_dashboard/doctor.py`

Every way into the program is a subcommand of `usb-lcd-dashboard`. `main(argv)`
lives at `cli.py:26`.

## Commands

| Command | Arguments | What it does | Exit |
| --- | --- | --- | --- |
| `run` | `--simulate` | Builds and runs the [daemon](../runtime/daemon.md). On Windows, logs to a file. | 0 |
| `emit` | `--provider claude\|codex` | Reads one JSON object from stdin, fires it at the daemon, exits. | 0 always |
| `statusline-proxy` | `--downstream-b64` | Forwards the status-line payload, then runs the user's original status-line command. | the downstream's code |
| `doctor` | `--paint-test` | Prints the check report; optionally paints a test frame. | 0 if all pass, else 1 |
| `install` / `uninstall` | — | See [install.md](install.md). | 0 |
| `shutdown` | — | Sends the control envelope. | 0, or 1 if it could not be sent |

Global `--verbose` switches logging to DEBUG.

`mcp` runs the local stdio server for the human todo tools and exits 0 at EOF.
It starts before config loading, because a broken display or IPC setting must
not prevent the user or an agent from managing the list.

## The hook commands never draw

`emit` and `statusline-proxy` are short-lived processes that read stdin, call
`send_event`, and exit. `_json_stdin` (`cli.py:18`) returns `{}` on a JSON parse
error rather than raising, so malformed input is dropped rather than crashing a
hook.

`statusline-proxy` always sends to the daemon **before** running the downstream
command, so the panel is fed even if the downstream fails. The downstream is
base64-encoded into the argument so an arbitrary shell command survives being
embedded in JSON settings; it runs with `NO_WINDOW` so no console flashes on
Windows.

## Strict loading is decided here

```python
config = load_config(strict=args.command == "run")
```

`cli.py:53-62`. Only `run` needs a layout it can draw. See
[../runtime/config.md](../runtime/config.md#strict-vs-lenient-loading) for the
full reasoning and [../architecture/invariants.md](../architecture/invariants.md).

## doctor

`doctor.py`. The command you run *because* something is wrong, so the one thing
it must never do is fail the way the thing it is diagnosing failed.

| Check | Passes when |
| --- | --- |
| `device` | A port matching the panel resolved. |
| `read/write access` (POSIX) | `os.access(device, R_OK\|W_OK)`. |
| `layout` | `layout_error` is empty **and** there is at least one agent slot. |
| `Claude hooks` / `Codex hooks` | The settings file mentions the emit command. |
| `Claude hook timeout` / `Codex hook timeout` | Every managed hook allows at least five seconds. |
| `hook emitter` | A synthetic emitter process completes within three seconds. |
| `Claude todo tools` / `Codex todo tools` | The user MCP configuration names the todo server. |
| `login autostart` (Windows) | The Startup shortcut exists. |
| `systemd` / `service` (POSIX) | `systemctl` exists; the unit is active. |

`print_report` returns whether everything passed, which becomes the exit code —
so `doctor` is usable as a post-install self-test. On a fresh install with the
panel unplugged it correctly exits 1.

`--paint-test` draws a card whose every line is derived from live config rather
than hardcoded, so it stays useful on a panel that is not the 3.5" Turing.

Two coupling notes: `_hook_present` greps the settings file for the literal
command string `install.py` writes, so the two files are tied by that substring;
and `checks()` requires a lenient config, or a broken layout would raise before
it ever ran.

## See also

- [install.md](install.md) — what `install` actually does.
- [../runtime/transport.md](../runtime/transport.md) — where `emit` sends.
- [../reference/commands.md](../reference/commands.md) — copy-pasteable recipes.
