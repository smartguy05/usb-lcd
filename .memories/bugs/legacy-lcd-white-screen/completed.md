# Completed

- Diagnosed the white screen as a mixed display profile: legacy transport plus wide-panel canvas and tiles.
- Updated the settings editor so selecting the legacy/auto serial transport restores the orientation-correct 480x320 profile and full-screen legacy tile.
- Added a regression assertion covering the legacy profile reset in the served editor page.
- Focused tests pass (107 tests). The full applicable suite passes with one expected skip when the pre-existing Windows-incompatible `cat` command test is excluded.
- Rebuilt both 0.10.0 installers from the fixed tree. The Debian package passed its Ubuntu 24.04 smoke test; metadata is `0.10.0`, `all`, installed size 580 KiB.
- Updated README, Windows, and Linux SHA-256 values for the rebuilt artifacts.
- Documented the immediate recovery for the already-mixed active config: install the rebuilt package, select `turing_rev_a` again, and save so the new editor writes the legacy profile.
- Corrected the install guide's managed-hook timeout from 5 to 10 seconds and documented the settings editor's legacy/auto profile reset.
