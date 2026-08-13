# Integration

How the dashboard attaches itself to Claude Code and Codex, and how to check
that it did.

| Document | Covers |
| --- | --- |
| [cli.md](cli.md) | Every subcommand, and what `doctor` checks. |
| [install.md](install.md) | Hook merging, the status-line proxy, the systemd unit. |

## Where to start

**"Nothing appears on the panel"** → run `doctor` ([cli.md](cli.md#doctor)). It
checks the device, read/write access, the layout, both hook files, and the
service, and its exit code is usable as a self-test.

**"How does a hook reach the daemon?"** →
[../architecture/overview.md](../architecture/overview.md).

**Adding a hook event** →
[../reference/phases.md](../reference/phases.md#adding-a-phase). Registering it
in `install.py` is the step people forget; without it the phase is mapped but
unreachable, which is exactly what happened to `NOTICE`.

## The rule that governs this whole area

A hook must never fail because of the dashboard. It exits 0 when the daemon is
absent, and it tolerates a config layout it will never draw. One bad tile rect
used to make every hook in every session dump a traceback — see
[../architecture/invariants.md](../architecture/invariants.md).

## See also

- [../packaging/README.md](../packaging/README.md) — the system-level half of installing.
- [../runtime/transport.md](../runtime/transport.md) — where `emit` sends.
