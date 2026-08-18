# Notes

- Both hook targets returned zero when invoked directly with a Stop payload.
- The failures occur at the hook runner boundary; observational commands should
  therefore explicitly normalize failures to success.
- Follow-up inspection found the prior completion record did not match the tree:
  `_merge_hooks` still emitted bare commands with 5-second timeouts, and the
  installed Claude and Codex settings consequently retained those values.
- Both installed Stop targets return zero with representative input when run
  directly through Git Bash. The failure remains intermittent/runner-boundary,
  so the generated command must guarantee success even when the emitter fails.
- Codex runs Windows hooks with Windows PowerShell, not Git Bash. A quoted
  executable without `&` is only a string expression, and PowerShell 5.1 also
  rejects `||`; the generated command therefore failed before launching the
  emitter. Claude still needs the existing Bash form.
- An August 18 hook audit found the installed user-level Codex hooks corrected,
  but the repository-local `.codex/hooks.json` still has the old quoted
  code-basics commands without `&`; both `PostToolUse` and `Stop` fail parsing.
- Repository-local Codex hook configuration is independent of the installed
  user-level dashboard hooks and needs the same PowerShell-safe, non-fatal form.
- Codex snapshots repository-local hooks for a running session. Editing
  `.codex/hooks.json` repairs new sessions but does not replace the stale Stop
  command already loaded by the session in which the edit was made.
