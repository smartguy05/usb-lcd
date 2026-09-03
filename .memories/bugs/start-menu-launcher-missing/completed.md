# Completed

- Diagnosed from installed shortcut targets plus `dashboard.log`: the Start-menu
  folder had no launcher, so the clicked entry ran `doctor` and exited.
- Confirmed the daemon itself was healthy by launching the Startup shortcut
  (LCD connected at COM10, tray up, no "Tray icon unavailable").
- Added the `$SMPROGRAMS` launcher in `installer.nsi` with a regression test.
- Corrected the shortcut list in `docs/packaging/windows.md` and documented
  restart-after-Quit in `WINDOWS.md`.
- Bumped to 0.12.1, rebuilt both installers, synced hashes and sizes in
  `README.md` / `WINDOWS.md` / `LINUX.md`, added the changelog entry.
- 582 tests pass (8 platform skips); docs `--check` clean; Debian smoke test
  passed.
