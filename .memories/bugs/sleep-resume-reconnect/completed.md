# Completed

- Diagnosed the stale-daemon/hidden-second-launch failure mode from installed process and log state.
- Added long-pause display reconnect and shortcut-triggered reconnect behavior with regression tests.
- Documented automatic and Start-menu recovery in `WINDOWS.md` and the daemon runtime reference.
- Rebuilt Windows and Debian 0.10.0 installers; Debian smoke test passed.
- Verified Debian metadata (`0.10.0`, `all`, installed size 580) and synchronized SHA-256 hashes in user docs.
- Corrected the settings transition from legacy/auto to TURZX USB so PID 0092 receives its 1920x462 canvas and wide layout.
- Rebuilt both installers again; final Debian installed size is 584 and the smoke test passes.
- Repaired the live installed config to the 1920x462 wide profile, installed the corrected Windows build, and verified one daemon instance connected and wrote full frames.
- Diagnosed the 2026-09-04 legacy LCD recurrence from live process, PnP and log
  state, then restored it with a reconnect control and verified a new COM10 open
  plus a 480x320 full-frame write.
- Added **Settings → Display → Reconnect LCD** backed by a guarded HTTP endpoint
  that queues the existing daemon IPC control; added route/UI/daemon-wiring
  tests and documented the recovery action.
- Released the change as 0.12.2: full test suite and docs checks passed, both
  installers rebuilt, Debian smoke test passed, and metadata/hashes synchronized.
