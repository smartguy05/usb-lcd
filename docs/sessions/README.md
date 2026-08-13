# Sessions

What a Claude Code or Codex session looks like to this program, and which one
gets to be on screen.

| Document | Covers |
| --- | --- |
| [normalize.md](normalize.md) | Hook payload to `SessionState`, both providers, and the activity line. |
| [model.md](model.md) | `SessionState`, the merge rules, and the tile arbiter. |

## Where to start

**"Why is this session not showing?"** →
[model.md](model.md#assign--the-arbiter). The usual answers are a TTL expiry,
the dwell floor, or the session having nothing new to show.

**"Why did this field go blank?"** → [model.md](model.md#apply--merge-rules).
Most optional fields carry forward when absent; `activity` deliberately does
not, because a prompt or stop event carries no tool and its empty activity must
clear the stale one.

**"Where does this text come from?"** →
[normalize.md](normalize.md#the-activity-line).

## The subtlest code in the repository

`StateStore.assign()` is about 130 lines implementing eight interacting rules
about fairness and preemption: TTLs, freshness, approval preemption, dwell
floors, no relocation, no duplicates. Read `tests/test_state.py` alongside it —
those tests are the executable specification.

## See also

- [../reference/phases.md](../reference/phases.md) — the phase strings everything switches on.
- [../rendering/widgets.md](../rendering/widgets.md) — what consumes a `SessionState`.
