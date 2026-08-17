# Completed

- Captured the decision-complete work item and repository constraints.
- Added the SQLite todo schema, validation, CRUD/history/reorder operations, urgency ranking, and cached immutable snapshots.
- Added the responsive prioritized/paged todo renderer, registry capability, immutable tile context, and daemon snapshot wiring.
- Added loopback JSON todo CRUD/history/reorder endpoints and an immediate-save admin list editor.
- Added dependency-free stdio MCP tools with human-only instructions plus idempotent Claude/Codex install, uninstall, and doctor integration.
- Added store, renderer, admin, subprocess MCP, and installer lifecycle coverage; synchronized user/reference docs and regenerated the documentation indexes.
- Released metadata as 0.8.0; rebuilt the signed identity-aware Windows installer and Debian package, verified package contents/metadata and SHA-256 hashes, and passed the Ubuntu 24.04 smoke test.
- Final verification: 481 tests passed with 1 platform skip; documentation coverage/check and `git diff --check` passed.
