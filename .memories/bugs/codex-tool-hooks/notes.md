# Notes

- Codex 0.147.0 emits `hook/started` and `hook/completed` UI lifecycle events, but the dashboard log contains no real Codex events.
- Both installed `pythonw.exe` and `python.exe` successfully pipe synthetic Codex hook JSON into the running dashboard; the interpreter and ingestion path are healthy.
- `~/.codex/hooks.json` was written at 14:24:02 during an already-running Codex session. The next diagnostic is a fresh session, since the active session predates hook discovery and trust.
