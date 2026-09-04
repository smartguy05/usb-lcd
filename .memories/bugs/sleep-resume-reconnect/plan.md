# Plan

- [x] Inspect installed process state and dashboard log.
- [x] Add automatic stale-handle recovery after a long runtime pause.
- [x] Make a second shortcut launch request a reconnect from the existing daemon.
- [x] Add a web-settings action that queues the existing reconnect control over
      IPC, keeping USB operations on the daemon loop.
- [ ] Reproduce the legacy panel going black with COM still started and decide
      whether panel liveness can be queried or needs a bounded refresh watchdog.
- [x] Run regression tests.
- [x] Update runtime/user/packaging documentation.
- [x] Rebuild and verify both installers.
