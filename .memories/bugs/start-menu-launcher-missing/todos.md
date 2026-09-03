# Todos

- [x] Add the Start-menu launcher to `installer.nsi`.
- [x] Regression test in `tests/test_windows_installer.py`.
- [x] Update `docs/packaging/windows.md` and `WINDOWS.md`.
- [x] Bump 0.12.1, rebuild both installers, sync hashes.
- [ ] Install the 0.12.1 exe on this machine and confirm Quit -> Start-menu
      relaunch restores the tray icon. Not yet done.
- [ ] Unrelated, found while diagnosing: `dashboard.log` never rotates (79 MB
      here) and `notifications.py:244` logs a full traceback every ~2.5s
      (`app_user_model_id` -> `OSError WinError -2147467263`, 94,144 of them).
