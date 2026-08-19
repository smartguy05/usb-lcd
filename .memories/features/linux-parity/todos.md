# Todos — Linux parity

## Done (verified on hardware 2026-08-19)
- [x] apt deps + udev rule installed
- [x] Panel drawing at 1920x462 over native USB
- [x] Tray icon appears; menu opens settings and log folder
- [x] .deb rebuilt at 0.11.0, smoke test passes
- [x] systemd unit re-pointed at /usr/bin; verified running from the package
      with NO venv gi symlink involved (system python resolves gi, pyusb
      1.2.1 and Cryptodome)
- [x] Committed on branch feat/linux-tray-and-turzx-panel (f4f1287)

## Outstanding
- [ ] dist/USB-LCD-Dashboard-Setup-0.11.0.exe does NOT exist. Runtime code
      changed on both platforms, so the Windows artifact is stale. Must be
      built from Windows Git Bash + Windows SDK (identity/MSIX signing);
      cannot be done from Linux. README's Windows SHA-256 cell is a
      placeholder until then.
- [ ] Four pre-existing doctor FAILs, unrelated to this work:
        Claude/Codex hook timeout (< 10s), Claude/Codex todo tools
      `usb-lcd-dashboard install` should repair all four. NOT run yet because
      it rewrites ~/.claude/settings.json, and the hooks fire on every tool
      use in a live Claude Code session.
- [ ] dist/usb-lcd-dashboard_0.10.0_all.deb is dirty in git from BEFORE this
      work (same size, different bytes). Left uncommitted deliberately.
      Superseded by 0.11.0 — user's call whether to delete or restore.
- [ ] The dev .venv still has the `gi` symlink and pip-installed
      pyusb/pycryptodome. Harmless, but a fresh venv wants
      `--system-site-packages` for the tray.
