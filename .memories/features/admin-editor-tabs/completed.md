# Completed

## 2026-08-19 — full rework, verified on a live daemon

**Files:** `src/usb_lcd_dashboard/admin_page.py` (the whole `PAGE` string),
`tests/test_admin.py` (+3 structural tests), `docs/admin/settings-editor.md`,
`README.md`, `WINDOWS.md`, `LINUX.md`, `packaging/linux/changelog`,
`dist/usb-lcd-dashboard_0.11.0_all.deb` (rebuilt).

**Shape now:** header → always-visible stage → collapsed `<details>` Settings
panel (Background / Screen saver / Display) → tabstrip (Live panel / Widget
settings). Clicking or adding a tile jumps to the widget tab.

**Contextual sections** are driven by the `wants_*` flags already on
`/api/widgets`, via `showContextSections()` — no hardcoded widget-name list:
`wants_session`→Dashboard, `wants_messages`→Discord, `wants_notifications`→
Windows notifications, `wants_todos`→Human todos. Read-only block always shows.

**Also done:** split the 114-line `drawSideForms()` into five builders plus
`drawPanels()`; scoped `syncTileNumbers()` to `#tileForm`; gated the 2s
`/api/preview.png` poll on tab visibility; `drawReadonly()` now re-runs from
`drawTileForm()` so the agent-slot count tracks tile edits; fixed five
double-encoded UTF-8 strings (`Loading todosâ€¦`, the todo reorder arrows, …).

**Input polish:** `field()` took a 7th `attrs` param. `color` options render a
chip + text box, `LABELS` humanises option names, `RANGES` supplies
min/max/step. All three are presentation-only lookups in the JS.

**Verified:** 554 tests pass; docs `--check` clean; deb rebuilt (sha256
`8095f612…6fa3e2`, README updated) and smoke-tested. Driven in a real browser
against a scratch daemon: tab switching, contextual swap for every widget,
drag→number sync, empty state, add-tile, save round trip reaching disk and the
rendered frame, narrow viewport, preview poll stopping while hidden.
