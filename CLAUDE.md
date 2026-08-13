# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## CRITICAL: Memory Files

**ALWAYS update the per-work-item memory files when relevant.** Memory is scoped **per feature/bug** under `.memories/features/{feature-name}/` or `.memories/bugs/{bug-name}/`, not at the `.memories/` root. These files track work item state across sessions:

| File | Path | Purpose | When to Update |
|------|------|---------|----------------|
| `work-item.md` | `.memories/features/{feature-name}/work-item.md` or `.memories/bugs/{bug-name}/work-item.md` | The feature work item details, ACs, description | When loading or refreshing work item context |
| `plan.md` | `.memories/features/{feature-name}/plan.md` or `.memories/bugs/{bug-name}/plan.md` | Implementation plan for the feature or bug fix | When planning or revising the approach |
| `related-docs.md` | `.memories/features/{feature-name}/related-docs.md` or `.memories/bugs/{bug-name}/related-docs.md` | Pointers to relevant documentation | When discovering docs that inform the work |
| `notes.md` | `.memories/features/{feature-name}/notes.md` or `.memories/bugs/{bug-name}/notes.md` | Issues, gotchas, lessons learned **for this work item** | When debugging/solving something others might hit on this WI |
| `todos.md` | `.memories/features/{feature-name}/todos.md` or `.memories/bugs/{bug-name}/todos.md` | Remaining tasks and tech debt **for this work item** | When adding, completing, or deprioritizing tasks |
| `completed.md` | `.memories/features/{feature-name}/completed.md` or `.memories/bugs/{bug-name}/completed.md` | Completed work record (files touched, root cause, fix) | When finishing the work item (or a major phase of it) |

**Rules:**
1. Update these files **AT ALL TIMES** under the active work item folder — they are that work item's memory.
2. Update `completed.md` immediately after finishing a task (not at end of session).
3. Update `todos.md` to check off completed items and add new discovered tasks.
4. Update `notes.md` with any issue you debug/solve that others might hit.
5. Keep entries concise but descriptive — future you needs to understand.
6. Periodically prune `todos.md` to remove old completed items.
7. Periodically summarize and prune `completed.md` to keep the file size small.
8. **Cross-work-item patterns** (gotchas that recur across multiple work items) belong in `CLAUDE.md` (root or the relevant per-project `CLAUDE.md`), not in any single work item's `notes.md`.

## CRITICAL: Use `docs/` before reading source

`docs/` holds reference documentation written for you, not for end users, plus
two indexes that answer "where is this?" and "what explains this?" in one cheap
lookup. **Use them before grepping the tree or reading a whole module** — that
is what they are for.

```bash
python docs/tools/search.py --symbol assign    # where is it defined?
python docs/tools/search.py --file crab.py     # what is in this file, and which docs cover it?
python docs/tools/search.py tile arbitration   # which doc explains this?
python docs/tools/search.py --check            # do the docs still match the code?
```

Every result is one line with a path and a line number, so the next step is a
targeted read of a few lines rather than a whole file:

```text
src/usb_lcd_dashboard/model.py:117  [method] def assign(self, slots: int, ...)  # Place live sessions into `slots` tiles.
```

Suggested order of attack for any task:

1. `docs/README.md` — the map, and a "I want to…" table.
2. `python docs/tools/search.py <topic>` — narrow to the right document.
3. That document — it carries `file.py:LINE` references straight into the code.
4. Only then open the source, at the lines you were pointed at.

`docs/architecture/invariants.md` is required reading before any structural
change. Most of the rules there exist because breaking them caused a real bug.

### Keeping the docs true

The indexes are generated and committed. After adding, moving or renaming a
symbol, and before committing any documentation change:

```bash
python docs/tools/build_index.py     # rebuild; names any source file no doc covers
python docs/tools/search.py --check  # re-resolves every cited line and every relative link
```

`--check` fails on a citation that now points past the end of a file, a broken
relative link, and a source file no document covers. Both scripts are
stdlib-only and run on Windows and Linux.

When a document and the code disagree, **the code is right and the document is
stale** — fix the document as part of your change. Each document declares what
it covers in a `Covers:` line near the top; a new source file needs one, or
`--check` will fail.

## What this is

A Python daemon that draws a live Claude Code / Codex session dashboard onto a
Turing 3.5" USB LCD (480×320, USB `1a86:5722`, serial `USB35INCHIPSV2`), with a
tile system aimed at a second, not-yet-supported 1920×462 ultra-wide panel.
GPL-3.0-or-later, because `smartscreen-driver` is.

`docs/` is the reference material for changing the code; `README.md` is the
behavioural intent for using it — the *why* behind tile arbitration, the crab
widget, frame-rate limits, and both installers. The source is heavily commented
with the same rationale; those comments record measurements and past bugs, so
preserve them when editing nearby.

## Commands

```bash
python3 -m venv .venv
.venv/Scripts/pip install -e '.[test]'      # .venv/bin/pip on Linux
.venv/Scripts/pytest                        # 383 passing, ~13s
.venv/Scripts/pytest tests/test_layout.py::test_name -x
.venv/Scripts/usb-lcd-dashboard doctor
.venv/Scripts/usb-lcd-dashboard run --simulate    # writes ./screencap.png
```

There is no linter or formatter configured. `pytest` config lives in
`pyproject.toml` (`-q`, `testpaths = ["tests"]`).

Drive the simulator with a fake hook event over the real IPC path:

```bash
USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
  .venv/bin/usb-lcd-dashboard run --simulate
echo '{"hook_event_name":"PreToolUse","session_id":"a","cwd":"'"$PWD"'",
       "tool_name":"Edit","tool_input":{"file_path":"src/layout.py"}}' \
  | USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
    .venv/bin/usb-lcd-dashboard emit --provider claude
```

`USB_LCD_DASHBOARD_CONFIG` overrides the config path (`config.py:default_path`),
which is the only way to test against a config other than the installed one.

Packaging (containerised, so either target builds from either host; needs Docker
or Podman, `CONTAINER_RUNTIME=podman` to switch, version read from
`pyproject.toml`):

```bash
packaging/windows/build-installer.sh    # -> dist/USB-LCD-Dashboard-Setup-<v>.exe
packaging/linux/build-deb.sh            # -> dist/usb-lcd-dashboard_<v>_all.deb
packaging/linux/smoke-test.sh           # installs the .deb in a throwaway container
```

## Architecture

Events flow one way: **CLI hook → IPC → StateStore → tile assignment → compose →
Display diff → PanelDevice.**

- `cli.py` — every entry point. Hook invocations (`emit`, `statusline-proxy`)
  read one JSON object from stdin and fire it at the daemon, then exit; they
  never draw.
- `normalize.py` — provider-specific hook JSON → a single `SessionState`.
  `PHASES` maps hook event names to the phase strings widgets switch on
  (`TOOL`, `APPROVAL`, `NOTICE`, `COMPACTING`, …). Codex context usage is
  scraped from the tail of its transcript file.
- `activity.py` — rebuilds the human activity line ("Editing src/render.py")
  from tool name + tool input, mirroring Claude Code's own tool descriptions.
- `transport.py` — length-bounded JSON envelopes (`schema_version: 1`) over a
  Unix datagram socket (POSIX) or TCP loopback (Windows). `poll_timeout` is
  tied to the frame interval; a fixed value here used to cap the frame rate.
- `model.py` — `StateStore.apply` merges partial updates (absent optional
  fields inherit the previous value; `activity` deliberately does not).
  `StateStore.assign(slots)` is the tile arbiter: dwell floors, approval
  preemption, no relocation of a placed session. It is the subtlest code here
  and `tests/test_state.py` pins its rules.
- `layout.py` — `Tile` (explicit pixel rect + widget name), `validate`
  (overlap / off-screen / unknown widget, all naming the offending tile),
  `agent_slots` (session count derived *from* the layout), and `compose`, which
  renders each tile, isolates a raised widget to a `_fault_tile`, and composites
  over `background.py`.
- `widgets/` — a widget is `TileContext -> RGBA Image` of the tile's exact size.
  `widgets/__init__.py:WIDGETS` is the registry; each `WidgetSpec` declares
  `wants_session` and typed `Option`s, and `describe()` feeds those to the
  settings editor, so registering a widget is all it takes to get a working
  form and a session slot. Use `widgets/base.py:new_tile` so the tile honours
  `background`/`opacity`.
- `display.py` / `device.py` — `Display` owns dirty-rect diffing (crop unless
  the diff exceeds 70% of the frame); `PanelDevice` owns the wire.
  `SerialPanel.health_check` detects the driver silently reopening the port
  after a replug, which otherwise paints crops at stale offsets.
  `WindowPanel` raises on purpose — the ultra-wide's transport is unknown.
- `admin.py` / `admin_page.py` — the drag-a-rect settings editor on
  `127.0.0.1:45723`, inside the daemon so it can show the live frame. It saves
  by round-tripping through `parse_config_text` and `write_config`; the daemon
  notices the changed bytes and reloads. The file is the only channel between
  the two threads.
- `tray.py` — Windows notification-area icon (the daemon runs under
  console-less `pythonw.exe`, so it is the only visible sign of life).
- `install.py` — merges hooks into `~/.claude/settings.json` and
  `~/.codex/hooks.json` idempotently, identifying its own entries by the
  `usb-lcd-dashboard` substring; preserves any existing Claude status line by
  base64-encoding it behind `statusline-proxy`; writes and starts the systemd
  user unit on Linux. `install-state.json` records what to undo.

### Invariants to respect

- **Strict vs lenient config loading.** `cli.py` passes `strict=True` only for
  `run`. Everything else loads leniently and substitutes the default layout,
  recording why in `Config.layout_error`. A bad tile rect must never make hooks
  traceback in every session or block the `install` that would repair the file.
- **The 3.5" panel is pixel-frozen.** `tests/test_legacy_identical.py` renders
  through `compose` and through `render.py:render_dashboard` in one process and
  asserts identical pixels. `compose` has a fast path returning a single opaque
  full-screen tile's image untouched. `render.py` keeps its own duplicated
  context-bar drawing on purpose (see the note in `widgets/base.py`); don't
  "deduplicate" it.
- **`config.py` is the single source of config truth.** Defaults live in the
  `Config` dataclass; `default_config_toml` renders the example/installed TOML
  *from* them and a test asserts the examples match. Adding a setting means
  touching `Config`, `parse_config` and `dump_config_toml` (which round-trips —
  tomllib cannot write).
- **The serial link caps the frame rate at ~2.4 fps**, so nothing in a widget
  should oscillate above ~0.63Hz, and nothing should animate at a tile's outer
  edge (it dirties the whole tile and triples the bytes). `README.md` has the
  measurements.
- **Failures degrade, never crash the panel.** Widget fault → fault tile;
  compose fault → skip the frame; bad config reload → keep the last good one;
  editor or tray unavailable → log and carry on.
- `packaging/**` shell scripts, `postinst`, `postrm` and the udev rule are
  pinned to LF in `.gitattributes` — a CRLF makes `dpkg` ship an unrunnable
  `postinst`.

### Live-daemon hazard

A real daemon may already hold IPC port 45722 (Windows) or the Unix socket. A
test daemon started without a spare port will bind-fail or feed the user's
physical panel. Use `USB_LCD_DASHBOARD_CONFIG` with a distinct `ipc.port` and
`admin.port`. Never run `dist\*.exe` to inspect it — NSIS `/S` performs a full
install, not an extraction.

## Docs to keep in sync

`README.md` (behaviour, install, versions), `WINDOWS.md`, `LINUX.md`,
`config.example.toml`, `config.example.wide.toml`, `packaging/linux/changelog`,
and the version in `pyproject.toml` — the docs quote version-stamped filenames
and an installer sha256.

Plus `docs/`, which is verified rather than remembered: run
`python docs/tools/build_index.py && python docs/tools/search.py --check`. It
will tell you which documents you have invalidated.
