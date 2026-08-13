# Phases

The strings widgets switch on. Defined by `PHASES` in `normalize.py:12`,
registered by `EVENTS_BY_PROVIDER` in `install.py:26`.

## The table

| Hook event | Phase | Registered? |
| --- | --- | --- |
| `SessionStart` | `READY` | both |
| `UserPromptSubmit` | `THINKING` | both |
| `PreToolUse` | `TOOL` | both |
| `PermissionRequest` | `APPROVAL` | both |
| `PostToolUse` | `THINKING` | both |
| `PostToolUseFailure` | `ERROR` | **Claude only** |
| `Notification` | `NOTICE` | both |
| `Stop` | `DONE` | both |
| `SessionEnd` | `ENDED` | both |
| `PermissionDenied` | `THINKING` | **never fires** |
| `PreCompact` | `COMPACTING` | **never fires** |
| `PostCompact` | `THINKING` | **never fires** |
| *(anything else)* | `ACTIVE` | the fallback |

The last three are mapped but no hook is installed for them, so they cannot
occur in practice. `COMPACTING` has widget artwork that is currently
unreachable. Adding the hook to `COMMON_EVENTS` is all it would take.

A payload with no `hook_event_name` is treated as the synthetic event
`StatusLine` and forced to `ACTIVE`.

## Who cares about which

| Phase | Consequence |
| --- | --- |
| `TOOL` | Gets `tool_ttl` (900 s) instead of `active_ttl` (180 s) in [`StateStore`](../sessions/model.md), because a tool call emits nothing until it returns. |
| `APPROVAL` | Preempts tile assignment, ignoring the dwell floor. Accent goes `WARNING`. In the crab, triggers the alarm. |
| `NOTICE` | Also triggers the crab alarm, in `CLAUDE` orange rather than yellow so the two are distinguishable. |
| `ERROR` | Accent goes `ERROR` red. The crab droops. |
| `ENDED` | Sets `ended=True`; the session stops being live. The crab sleeps. |
| `DONE` | The crab settles into a content resting pose. |
| `TOOL`, `THINKING`, `ACTIVE` | The headline shows `state.activity` rather than the phase word. |

`ALARM_PHASES` and `SLEEPING_PHASES` in `crab.py:58-59` key off exactly these
strings.

## Adding a phase

1. Map the event in `PHASES`.
2. Register the hook in `COMMON_EVENTS` or `EVENTS_BY_PROVIDER`, or it will
   never fire. `tests/test_install.py::test_every_installed_event_maps_to_a_phase`
   guards the other direction.
3. Decide whether it needs a TTL rule in `StateStore._ttl`.
4. Give the widgets something to show for it — at minimum check `_accent` and
   `crab_pose` handle it; both fall through to a sensible default.
5. Users must re-run `usb-lcd-dashboard install` to get a newly registered hook.

## See also

- [../sessions/normalize.md](../sessions/normalize.md)
- [../sessions/model.md](../sessions/model.md)
- [../integration/install.md](../integration/install.md)
