# install.py — wiring into Claude and Codex

> **Covers:** `src/usb_lcd_dashboard/install.py`

Merges hooks and human-todo MCP tools into the user's CLI settings, preserves an existing status line,
seeds a config, and on Linux writes and starts a systemd user unit. Everything
it does is recorded in `install-state.json` so `uninstall` can undo it.

This is **per-user** work. It is never done by a package's `postinst`, which
runs as root and would wire the dashboard into root's sessions and nobody
else's — see [../packaging/linux.md](../packaging/linux.md).

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `COMMON_EVENTS`, `EVENTS_BY_PROVIDER` | `install.py:17`, `:26` | Which hooks get registered. |
| `install(executable=None)` | `install.py:123` | The whole sequence. |
| `uninstall()` | `install.py:201` | Reverse it. |
| `_command_prefix(explicit=None)` | `install.py:74` | The command written into hooks and the unit. |
| `_merge_hooks(settings, provider, prefix)` | `install.py:98` | Idempotent merge. |
| `_systemd_enable()` / `_systemd_disable()` | — | `daemon-reload` + `enable --now`, and the reverse. |

## Registered events

`COMMON_EVENTS` for both providers: `SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PermissionRequest`, `PostToolUse`, `Notification`, `Stop`,
`SessionEnd`. Claude additionally gets `PostToolUseFailure`.

`Notification` is what makes the `NOTICE` phase reachable — it was mapped in
`PHASES` long before any hook was registered for it, so the phase existed but
could never fire. `tests/test_install.py::test_every_installed_event_maps_to_a_phase`
stops the two lists drifting apart again. See
[../reference/phases.md](../reference/phases.md).

## How the command is resolved

`_command_prefix` looks for a console script **beside `sys.executable`**. In a
venv that finds `.venv/bin/usb-lcd-dashboard`; with the Debian package it finds
`/usr/bin/usb-lcd-dashboard` next to `/usr/bin/python3`. If there is no such
script it falls back to `<python> -m usb_lcd_dashboard`, which is what the
Windows payload uses since it installs no console script.

This is why the `.deb` ships a real script at `/usr/bin/usb-lcd-dashboard`
rather than a symlink somewhere else.

## What `install()` does

1. Create the state directory; load `install-state.json` if it exists, so a
   re-run is idempotent.
2. **Back up** the hook files plus `~/.claude.json` and `~/.codex/config.toml` — once ever,
   guarded by a key in the state file, so re-running never overwrites the
   original backup with an already-modified file.
3. **Preserve the status line.** The existing `statusLine` command is captured
   into state and base64-encoded into
   `statusline-proxy --downstream-b64 <…>`. If the existing command is already
   ours, the stored one is reused, so re-running never chains the proxy into
   itself.
4. **Merge hooks.** `_merge_hooks` strips any group whose JSON contains
   `usb-lcd-dashboard` or `usb_lcd_dashboard` — that substring is how it
   identifies its own entries — then appends a fresh one with `timeout: 5`.
   Other tools' hooks are left alone. Written atomically.
5. **Merge todo MCP tools.** Add a user-scoped stdio server to Claude Code and
   Codex without rewriting unrelated settings; record a displaced same-name
   entry so uninstall can restore it.
6. **Seed the config** only if none exists, with the platform's device and IPC
   mode.
7. **On POSIX**, write `~/.config/systemd/user/usb-lcd-dashboard.service`, then
   `daemon-reload` and `enable --now`.
8. Write `install-state.json` and print what happened.

Hook commands load only the IPC table, not the display layout or renderer stack.
This keeps startup comfortably below the timeout when the panel is unplugged or
the daemon is stopped. Codex requires a fresh session and explicit trust through
`/hooks` after its hook file changes.

The Windows installer treats a nonzero `install` helper exit as fatal. It also
checks that `install-state.json` exists, but an older state file is never used
as a substitute for a successful hook merge during an upgrade.

### The unit

```ini
[Unit]
Description=Claude Code and Codex USB LCD dashboard
After=graphical-session.target

[Service]
Type=simple
ExecStart=<command prefix> run
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=<state dir> %t

[Install]
WantedBy=default.target
```

`ProtectHome=read-only` with `ReadWritePaths` means the daemon can write only
its own state directory and `$XDG_RUNTIME_DIR` (`%t`) — where the Unix socket
lives. `PrivateTmp=true` is why the `/tmp` fallback in `runtime_dir()` is not
usable under the unit; a systemd user unit always sets `XDG_RUNTIME_DIR`.

Starting is best-effort. There is no user manager inside a container, a chroot
or a package build, and an installer that failed there would be worse than one
that installs and prints the two commands to run by hand.

## `uninstall()`

Strips the hook groups from both files, removes empty event keys, restores the
captured `statusLine` (popping the key entirely if there was none), and on POSIX
**disables the unit before deleting it** — deleting first would leave a dangling
`default.target.wants` symlink and the daemon still running with the panel held
open.

It also removes the installed MCP entries and restores displaced entries. It
deliberately **keeps** `config.toml`, `todos.sqlite3`, backups, and
`install-state.json`.

## Re-run after upgrading

The set of registered hooks grows occasionally, and an existing install keeps
whatever it was set up with until `install` runs again. Merging rather than
replacing is what makes that safe.

## See also

- [cli.md](cli.md) — the commands that call this.
- [../sessions/normalize.md](../sessions/normalize.md) — what the hooks send.
- [../packaging/linux.md](../packaging/linux.md) — the system half.
