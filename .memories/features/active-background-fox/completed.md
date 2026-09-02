# Completed — active-background fox

## Backend (done, verified via simulator)
- `tools/make_fox_sprites.py` — procedural 6-frame red-fox run cycle; baked to
  `src/usb_lcd_dashboard/assets/fox/run_00..05.png`. Fox faces right; runtime
  flips for leftward. Visually verified (contact sheet).
- `config.py` — `ActiveBackgroundConfig` (enabled, scale, speed_min, speed_max,
  opacity), `Config.active_background` (default None), `_parse_active_background`,
  parse wiring, and `[active_background]` emitted in `dump_config_toml`. Round-trip
  verified; default stays None so example-drift tests pass.
- `active_background.py` — `ActiveBackground` stateful runner. Loads/scales
  frames per (size, scale); `step(dt, size)` integrates x by speed*dt, cycles
  gait by distance, dwells `DWELL_SECONDS` off-screen then re-enters the other
  side (constant direction wrap). CPU via psutil `cpu_percent` → speed lerp;
  psutil/art missing degrades to neutral speed / no draw. Opacity applied to
  whole layer.
- `layout.compose` — new `active_background` overlay param, painted over the
  wallpaper and under tiles; presence disables the legacy byte-identical fast
  path. Legacy pixel-freeze test still green.
- `daemon.py` — owns `self.active_bg`, built/reconfigured in `_apply_config`
  (kept across edits), stepped with a clamped wall-clock `fox_dt`; overlay passed
  to compose only outside the screensaver.
- Added `psutil` to venv (6.1.1). Guard-rail tests pass: test_config,
  test_legacy_identical, test_layout.

## Verified
- Config round-trip of the new block.
- Simulator render over the wide example: fox visible in inter-tile gutters,
  occluded by opaque cards → correct z-order (behind tiles).

## Editor (done)
- `admin.py` config bridge: `active_background` in config_to_json/from_json.
- `admin_page.py`: third top-level tab "Active background" (#tabBtnActiveBg /
  #tabActiveBg / #activeBgForm), generalized `showTab` to a TABS loop,
  `drawActiveBgForm()` in drawPanels, save payload carries active_background.
  Checkbox presence == enabled.

## Packaging + docs (done)
- Version bumped to 0.12.0 (pyproject, __init__, installer.nsi).
- psutil: pyproject dep `psutil>=5.9,<8`; deb `python3-psutil` in control.
- Linux .deb 0.12.0 built (docker), sha256
  4eca6f056f9b758e0ec52e21b6ab5c261f062e515e59d79864ed7bb7597f49d1;
  smoke-test passed; fox assets + psutil dep verified inside the .deb.
- Docs: README fox section + 3-tab editor text + version refs; LINUX version+hash;
  WINDOWS + README "pending Windows build" notes; changelog 0.12.0;
  docs/rendering/active-background.md (Covers). Index rebuilt, --check clean.

## Windows installer — NOT built (environment blocker)
Cannot build the identity-enabled .exe from Linux. installer.nsi is at 0.12.0;
user must run packaging/windows/build-installer.sh on Windows and record the exe
+ sha256 in WINDOWS.md/README.

## Tests: 581 passed.

