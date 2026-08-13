# Documentation

Reference material for working on this repository, written so an agent can find
what it needs without reading the source tree.

**If you are looking something up, start with the
[search tool](tools/README.md)** — it is cheaper than grepping:

```bash
python docs/tools/search.py --symbol assign     # where is this defined?
python docs/tools/search.py --file crab.py      # what is in this file?
python docs/tools/search.py tile arbitration    # which doc explains this?
```

## The map

| Area | Start here | Covers |
| --- | --- | --- |
| **Architecture** | [architecture/](architecture/README.md) | The end-to-end flow, the invariants, the frame budget. |
| **Runtime** | [runtime/](runtime/README.md) | The daemon loop, config, IPC, the panel. |
| **Rendering** | [rendering/](rendering/README.md) | Tiles, widgets, the crab, palette and fonts. |
| **Sessions** | [sessions/](sessions/README.md) | Hook payloads to state, and which session is on screen. |
| **Integration** | [integration/](integration/README.md) | The CLI, hooks, `install`, `doctor`. |
| **Admin** | [admin/](admin/README.md) | The settings editor and the Windows tray. |
| **Packaging** | [packaging/](packaging/README.md) | Both installers and their builds. |
| **Testing** | [testing/](testing/README.md) | The suite, its idioms, and its hazards. |
| **Reference** | [reference/](reference/README.md) | Config keys, phase strings, command recipes. |

## Common tasks

| I want to… | Read |
| --- | --- |
| Understand the whole thing | [architecture/overview.md](architecture/overview.md) |
| Change anything structural | [architecture/invariants.md](architecture/invariants.md) **first** |
| Add a widget | [rendering/widgets.md](rendering/widgets.md#adding-a-widget) |
| Add anything animated | [architecture/frame-budget.md](architecture/frame-budget.md) |
| Add a config setting | [runtime/config.md](runtime/config.md#adding-a-setting) |
| Add a hook event or phase | [reference/phases.md](reference/phases.md#adding-a-phase) |
| Work out why a session is not on screen | [sessions/model.md](sessions/model.md#assign--the-arbiter) |
| See the frame on the panel right now | [admin/README.md](admin/README.md) |
| Run or simulate the app | [reference/commands.md](reference/commands.md) |
| Build an installer | [packaging/README.md](packaging/README.md) |
| Write a test | [testing/README.md](testing/README.md) |

## How this documentation is kept honest

Each document declares the source files it covers in a `Covers:` line near the
top. [`build_index.py`](tools/README.md) turns those into a reverse map and
reports any source file nothing covers; `search.py --check` re-resolves every
`file.py:LINE` citation and fails on the ones that have rotted.

```bash
python docs/tools/build_index.py
python docs/tools/search.py --check
```

Run both after moving code, and before committing a documentation change.

## What is not here

- **User-facing install and behaviour docs** live at the repo root:
  `README.md`, `WINDOWS.md`, `LINUX.md`. This directory is for people changing
  the code, not running it.
- **The rationale behind individual lines** lives in the source comments, which
  record measurements and past bugs. These documents point at them rather than
  copying them; when the two disagree, the code is right and the document is
  stale.
