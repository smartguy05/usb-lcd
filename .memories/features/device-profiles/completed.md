# Completed

- Captured requirements and identified size-based auto-detection as the root limitation.
- Added hardware-keyed profile detection, migration, persistence, and daemon switching.
- Added profile tests and documented Windows/Linux behavior.
- Changed the editor's Auto selection to preserve the current layout instead
  of applying the legacy fixed-size preset.
- Passed the full test suite (568 runnable, 8 skipped), detected the live
  `turzx-0092`, rebuilt both 0.11.0 installers, and passed the Debian smoke test.
- Verified Debian metadata (`all`, installed size 624) and synchronized final
  hashes: Windows `1e00f92c...39108746`; Debian `405ed854...60d3cbe`.
