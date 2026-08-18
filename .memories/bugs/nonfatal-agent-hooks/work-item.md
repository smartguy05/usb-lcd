# Non-fatal agent hooks

Ensure the USB LCD event emitter and code-basics intent recorder cannot report
agent hook failures when optional telemetry is unavailable.

## Acceptance criteria

- Claude hook commands are non-fatal and have sufficient startup time.
- Codex intent hooks are non-fatal and have sufficient startup time.
- Both Stop-hook targets still accept a representative payload.
- Codex hooks use syntax accepted by the Windows PowerShell hook runner.
