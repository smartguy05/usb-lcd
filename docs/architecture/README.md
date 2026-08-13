# Architecture

How the pieces fit, and the rules that hold across all of them. Start here if
you are new to the repository.

| Document | Read it when |
| --- | --- |
| [overview.md](overview.md) | You need the end-to-end path from a hook firing to a pixel changing. |
| [invariants.md](invariants.md) | **Before any structural change.** Every rule here exists because breaking it caused a real problem. |
| [frame-budget.md](frame-budget.md) | You are adding anything that moves, or wondering why the panel is slow. |

## The one-paragraph version

A hook fires, `cli.py` throws one JSON object at a socket and exits. The daemon
loop reads at most one event per tick, normalises it into a `SessionState`,
merges it into the store, asks the store which sessions get screen time,
composes a frame from the tiles, diffs it against the last frame, and sends only
what changed. Nothing reads back up the chain.

## See also

- [../runtime/README.md](../runtime/README.md) — the loop and the wire.
- [../rendering/README.md](../rendering/README.md) — how a frame is drawn.
- [../sessions/README.md](../sessions/README.md) — what a session is.
