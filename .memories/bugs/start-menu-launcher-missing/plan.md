# Plan

1. Add `CreateShortCut "$SMPROGRAMS\USB LCD Dashboard\USB LCD Dashboard.lnk"`
   to `packaging/windows/installer.nsi`, same command as the Startup shortcut.
2. Pin it with a test in `tests/test_windows_installer.py`.
3. Fix the docs that already described the missing shortcut
   (`docs/packaging/windows.md` shortcut list, `WINDOWS.md` tray section).
4. Bump to 0.12.1 and rebuild both installers; 0.12.0's exe was already
   published with a recorded hash, so it must not be overwritten in place.
