# TODOs — active-background fox

## Done
- [x] Sprite generator `tools/make_fox_sprites.py` + baked PNGs (run_00..05)
- [x] `active_background.py` stateful renderer (step/reconfigure, CPU→speed, dwell)
- [x] `config.py` ActiveBackgroundConfig + parse + dump + validation
- [x] `layout.compose` overlay param + fast-path guard
- [x] `daemon.py` owns/steps ActiveBackground; overlay to compose (not screensaver)
- [x] `pyproject.toml` psutil dep + version 0.12.0; assets verified in wheel
- [x] `packaging/linux/control` python3-psutil dep
- [x] admin editor: 3rd "Active background" tab, generalized showTab, config bridge
- [x] Tests: test_active_background.py, config round-trip+validation, layout overlay,
      admin 3rd tab + bridge. Full suite 581 passed.
- [x] Linux .deb 0.12.0 built + smoke-tested; assets + psutil dep verified inside
- [x] Docs: README (fox section + editor tab), LINUX (version+sha256), WINDOWS
      (pending note), changelog, docs/rendering/active-background.md, docs index
      rebuilt + --check clean (42/42)

## Remaining (blocked / for the user)
- [ ] Windows installer 0.12.0 — MUST be built on Windows (Git Bash + SDK).
      installer.nsi bumped to 0.12.0; WINDOWS.md/README carry a "pending" note.
      After building, record dist/USB-LCD-Dashboard-Setup-0.12.0.exe + sha256.
- [ ] Pre-existing unrelated: dist/usb-lcd-dashboard_0.10.0_all.deb had a local
      modification at session start (not from this work).
- [ ] Commit (not done — waiting on user).
