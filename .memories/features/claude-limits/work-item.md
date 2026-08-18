# Claude limits widget

Add a responsive LCD widget for Claude's 5-hour, weekly, and Fable usage limits, including reset countdowns and durable last-known values. Harden dashboard hooks so telemetry remains fast and non-blocking.

## Acceptance criteria

- Native Claude session/weekly limits and OAuth-backed Fable limits render responsively.
- Credentials are never persisted, logged, or exposed in process arguments.
- Missing/stale sources degrade without breaking hooks or the dashboard.
- Hook emitters stay below their configured timeout when the display or daemon is unavailable.
- Documentation, versioned installers, metadata, smoke tests, and hashes are current.
