# Notes

- The live installation was 0.8.0 and both settings files still used two-second timeouts.
- The 0.9.0 installer checked only for an existing install-state file after running setup, so an upgrade could mask a nonzero setup-helper exit code.
- Codex loads hook definitions for a session; restart Codex after changing `~/.codex/hooks.json`.
