# Legacy LCD white screen

Switching from the new wide TURZX LCD back to the legacy Rev A LCD must restore a compatible 480x320 display profile so the daemon can connect and paint instead of leaving the panel white.

Acceptance criteria:
- Selecting `turing_rev_a` or serial `auto` in the settings editor restores the legacy panel's fixed dimensions.
- The incompatible wide tile layout is replaced by the full-screen legacy dashboard.
- New TURZX and simulated configurations remain customizable.
- Regression tests and both installer artifacts are current.
