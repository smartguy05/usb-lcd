# normalize.py — hook payload to SessionState

> **Covers:** `src/usb_lcd_dashboard/normalize.py`, `src/usb_lcd_dashboard/activity.py`

The single translation boundary between two providers' payload shapes and the
internal model. It is the only producer of `SessionState` from live traffic.

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `PHASES` | `normalize.py:12` | Hook event name to phase string. |
| `normalize_event(provider, payload, now=None)` | `normalize.py:75` | The whole job. |
| `describe_activity(tool, tool_input, cwd="")` | `activity.py:60` | The activity line. |
| `SUMMARY_LIMIT = 50` | `activity.py:17` | Cap on any free-text field. |

## Field sources

| `SessionState` field | From |
| --- | --- |
| `session_id` | `session_id` / `sessionId` / `turn_id`, else `f"{provider}-status"` |
| `phase` | `PHASES[hook_event_name]`, else `ACTIVE` |
| `detail` | `tool_name`; for `APPROVAL`, `tool_input.description` or `"User decision needed"` |
| `activity` | `describe_activity(tool, tool_input, cwd)` |
| `model` | `model.display_name` / `model.id`, or a plain string |
| `cwd` | `workspace.current_dir` / `cwd` / `workspace.project_dir` |
| `context_percent` | `context_window.used_percentage`, else `100 - remaining_percentage`, else the Codex scan |
| `input_tokens` / `output_tokens` | `context_window.total_input_tokens` / `..._output_tokens`, else the Codex scan |
| `cost_usd` | `cost.total_cost_usd` |
| `ended` | `phase == "ENDED"` |
| `extra` | `{"event": event}` — how `apply()` spots a `StatusLine` |

## Phases

The full table is in [../reference/phases.md](../reference/phases.md), including
which are reachable in practice. The short version: `PHASES` maps twelve event
names, `install.py` registers nine of them, and three (`PermissionDenied`,
`PreCompact`, `PostCompact`) are mapped but never fire because no hook is
installed for them.

A payload with no `hook_event_name` is treated as `StatusLine` and forced to
phase `ACTIVE` (`:81`, `:95-96`). Preserving the real phase across a status-line
tick is [`StateStore.apply`](model.md#apply--merge-rules)'s job, not this
module's.

## Context usage differs by provider

- **Claude** delivers it in the payload's `context_window`, but **only on the
  status-line payload** — ordinary hook events carry none, which is why the
  value is carried forward between ticks by `apply()`.
- **Codex** delivers none at all, only `transcript_path`. `_latest_codex_usage`
  (`normalize.py:41-72`) opens the transcript, seeks to the **last 2 MB**, and
  scans lines in reverse for the first `payload.type == "token_count"` record,
  computing `total_tokens * 100 / model_context_window`. A tail scan, not a full
  parse, so a long session does not cost more on every hook. A missing or
  unreadable file yields `{}`.

Codex therefore re-scans on every event, since its payloads never populate
`context_window`.

## The activity line

`describe_activity` rebuilds the line Claude Code prints above its own spinner,
from the tool name and input a hook already delivers. The phrasing mirrors the
tool definitions in Claude Code 2.1.223 so the LCD reads the same as the
terminal.

| Tool | Line |
| --- | --- |
| `Read` / `Write` | `Reading {path}` / `Writing {path}` |
| `Edit`, `MultiEdit` | `Editing {path}` |
| `NotebookEdit` | `Editing notebook {path}` |
| `Glob` / `Grep` | `Finding {pattern}` / `Searching for {pattern}` |
| `Bash`, `PowerShell` | `Running {description or command}` |
| `WebFetch` / `WebSearch` | `Fetching {url}` / `Searching for {query}` |
| `Task`, `Agent` | the description verbatim |
| `Monitor` / `Skill` | `Monitoring: {…}` / `Running skill {…}` |

Unknown tools — Codex and MCP servers — fall through a chain of `description`,
command, url, pattern/query, path, and finally the bare tool name
(`activity.py:98-110`), so something useful always appears.

`_short_path` (`:27`) shortens relative to `cwd`, else `~/`, else leaves it
absolute; a `ValueError` from differing Windows drive letters falls through
rather than raising. Everything is capped at 50 characters with an ellipsis.

## Tests

`tests/test_normalize.py` (field extraction for both providers, the Codex tail
scan, activity replacing the tool name, activity clearing on a tool-less event)
and `tests/test_activity.py` (a parametrised table of every tool plus unknown
ones, truncation, and non-dict `tool_input`).

## See also

- [model.md](model.md) — what happens to the result.
- [../integration/install.md](../integration/install.md) — which hooks are registered.
- [../reference/phases.md](../reference/phases.md) — the phase table.
