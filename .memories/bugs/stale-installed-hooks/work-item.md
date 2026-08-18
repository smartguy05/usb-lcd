# Work Item

Fix live Claude and Codex dashboard hooks that remained at the old two-second timeout after the 0.9.0 upgrade.

## Acceptance criteria

- Installed dashboard is version 0.9.0.
- Every managed live hook uses a five-second timeout and exits successfully.
- Windows upgrades cannot silently accept a failed hook/configuration merge.
