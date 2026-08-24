# Completed

- Added account-scoped persistent native Claude usage snapshots and a credential-safe, rate-limited background Fable refresh.
- Added the responsive `claude_limits` ring/bar renderer and daemon/compositor/registry wiring.
- Added lightweight IPC-only hook config loading, lazy CLI imports, five-second managed hook timeouts, and doctor checks.
- Targeted limits, widget, layout, config, install, transport, and doctor tests pass.
- Added source/cache/error-path and responsive render coverage; the full suite passes with one platform skip.
- Documented the limits source/security/degradation behavior and regenerated a fully covered documentation index.
- Visually inspected the final 480x320 render and adjusted the ring, rows, title, and stale marker for LCD legibility.
- Released version 0.9.0 artifacts: rebuilt the signed Windows installer and Debian package, then passed the Ubuntu 24.04 install/render/doctor/uninstall smoke test.
- Fixed stale session/weekly meters by retaining all buckets from the periodic
  OAuth usage refresh; added regression coverage and rebuilt both 0.11.0
  installers. The full test suite and Debian smoke test pass.
