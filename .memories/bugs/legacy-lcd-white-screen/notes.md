# Notes

- Active config reproduced the fault: `kind = "turing_rev_a"` with `width = 1920`, `height = 462`, and wide-panel tiles.
- `SerialPanel` correctly refuses any logical canvas whose native size is not 480x320. Because the mismatch is discovered before a frame write, the physical panel remains on its white power-on screen.
- The settings editor previously changed only `display.kind`; it retained dimensions and tiles from the prior panel.
# Notes

- Documentation audit found one stale `timeout: 5` statement in `docs/integration/install.md`; implementation and doctor threshold are 10 seconds.
- The editor's legacy/auto display-kind reset was implemented but previously undocumented; documented in `docs/admin/settings-editor.md`.
