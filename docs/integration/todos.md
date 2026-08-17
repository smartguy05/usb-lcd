# Human todos

> **Covers:** `src/usb_lcd_dashboard/todos.py`, `src/usb_lcd_dashboard/mcp.py`

One SQLite database, `todos.sqlite3` beside `config.toml`, is shared by the
daemon, settings-editor threads, and short-lived MCP server processes. Each
operation owns a connection and SQLite supplies cross-process locking. The
daemon caches an immutable `TodoSnapshot` for half a second; renderers never
query storage.

Items have a UUID, title, optional details, `urgent|high|normal|low` priority,
optional `YYYY-MM-DD` deadline, status, manual position, and timestamps.
Completing retains history; reopening appends to the open manual order;
permanent deletion requires explicit confirmation.

`usb-lcd-dashboard mcp` is a newline-delimited JSON-RPC stdio MCP server. It
exposes `list_todos`, `add_todo`, `update_todo`, `complete_todo`, and
`delete_todo`. Its server instructions define the boundary: this is only for
actions the human needs to take, never an agent's plan or scratch memory.

`install` adds the server at user scope to `~/.claude.json` and
`~/.codex/config.toml`. It preserves any displaced same-name entry in
`install-state.json`; `uninstall` restores it while retaining todo history.
