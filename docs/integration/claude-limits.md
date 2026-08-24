# Claude usage limits

> **Covers:** `src/usb_lcd_dashboard/claude_limits.py`

The `claude_limits` widget shows Claude subscription usage as a five-hour meter
plus weekly and Fable bars. Every available window includes its consumed
percentage and a countdown derived from the reset timestamp.

Claude Code sends `rate_limits.five_hour` and `rate_limits.seven_day` to the
dashboard's existing status-line proxy after an API response. The daemon
normalizes those values and saves them in `claude-limits.json` beside
`config.toml`, so the last known values survive dashboard restarts. Expired
windows disappear until Claude supplies a new value.

Claude Code does not expose model-scoped Fable usage through status-line JSON.
When a `claude_limits` tile is configured, a background worker therefore reads
Claude's current OAuth access token and calls the usage endpoint no more than
once every fifteen minutes. The refresh updates the five-hour and weekly values
as well as Fable, preventing native values from remaining stale when Claude has
not recently emitted a status-line payload. It sends the token only in the HTTPS
authorization header and never logs or persists it. The cache contains normalized
percentages and timestamps only, is scoped to the current Claude account, and is
mode 0600 on POSIX. A missing credential, offline host, changed response, or 429
keeps the last good value and never affects rendering or hooks.

The endpoint used for Fable is undocumented. If Anthropic removes it, the
Fable row hides while native five-hour and weekly reporting continues.

```toml
[[tile]]
widget = "claude_limits"
x = 12
y = 12
w = 480
h = 320
[tile.options]
title = "Claude"
```

Tall tiles use the circular session meter followed by compact bars. Short or
wide tiles use bar rows throughout. Unavailable rows are hidden; when no source
has supplied a live window, the tile says `WAITING FOR CLAUDE USAGE`.
