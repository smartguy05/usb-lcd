from datetime import datetime, timedelta, timezone

from usb_lcd_dashboard.model import SessionState, StateStore


NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)


def state(provider, session, phase, seconds=0):
    at = NOW + timedelta(seconds=seconds)
    return SessionState(provider, session, at, at, phase=phase, cwd="/work/demo")


def test_merges_sparse_updates():
    store = StateStore()
    store.apply(state("claude", "one", "READY"))
    update = state("claude", "one", "TOOL", 5)
    update.model = "Opus"
    merged = store.apply(update)
    assert merged.project == "demo"
    assert merged.model == "Opus"


def test_approval_has_priority_over_more_recent_work():
    store = StateStore()
    store.apply(state("claude", "one", "APPROVAL"))
    store.apply(state("codex", "two", "TOOL", 10))
    assert store.active(NOW + timedelta(seconds=11)).phase == "APPROVAL"


def test_stale_sessions_go_idle():
    store = StateStore(active_ttl=10)
    store.apply(state("codex", "one", "DONE"))
    assert store.active(NOW + timedelta(seconds=11)) is None


def test_statusline_refresh_preserves_phase():
    store = StateStore()
    store.apply(state("claude", "one", "DONE"))
    update = state("claude", "one", "ACTIVE", 1)
    update.extra["event"] = "StatusLine"
    assert store.apply(update).phase == "DONE"


def test_a_session_waiting_on_a_long_tool_call_stays_visible():
    store = StateStore(active_ttl=180, tool_ttl=900)
    store.apply(state("claude", "slow", "TOOL"))
    still_working = store.active(NOW + timedelta(seconds=400))
    assert still_working is not None and still_working.session_id == "slow"


def test_an_idle_session_still_expires_on_the_short_timeout():
    store = StateStore(active_ttl=180, tool_ttl=900)
    store.apply(state("claude", "finished", "DONE"))
    assert store.active(NOW + timedelta(seconds=400)) is None


def test_a_chatty_session_cannot_starve_a_quiet_one():
    """The failure this reproduces: one session emitting every second took every
    frame, so the other was never on screen long enough to read."""
    store = StateStore(switch_dwell=4.0)
    seen = []
    for tick in range(24):
        store.apply(state("claude", "chatty", "TOOL", tick))
        if tick % 8 == 0:
            store.apply(state("claude", "quiet", "TOOL", tick))
        shown = store.active(NOW + timedelta(seconds=tick))
        seen.append(shown.session_id)
    assert "quiet" in seen, "the quiet session never reached the screen"
    assert "chatty" in seen
    # Each turn must last long enough to read, not flicker frame to frame.
    runs = [session for index, session in enumerate(seen) if index == 0 or session != seen[index - 1]]
    assert len(runs) < len(seen) / 2


def test_a_session_with_nothing_new_does_not_take_a_turn():
    store = StateStore(switch_dwell=0.0)
    store.apply(state("claude", "one", "TOOL", 0))
    assert store.active(NOW).session_id == "one"
    store.apply(state("claude", "two", "TOOL", 1))
    assert store.active(NOW + timedelta(seconds=1)).session_id == "two"
    # "one" has now been shown and has nothing newer, so the holder keeps it.
    assert store.active(NOW + timedelta(seconds=2)).session_id == "two"
    store.apply(state("claude", "one", "TOOL", 3))
    assert store.active(NOW + timedelta(seconds=3)).session_id == "one"


def test_approval_preempts_the_dwell():
    store = StateStore(switch_dwell=30.0)
    store.apply(state("claude", "working", "TOOL", 0))
    assert store.active(NOW).session_id == "working"
    store.apply(state("claude", "asking", "APPROVAL", 1))
    assert store.active(NOW + timedelta(seconds=1)).session_id == "asking"


# --------------------------------------------------------------- several tiles


def ids(slots):
    return [None if s is None else s.session_id for s in slots]


def test_active_is_the_one_slot_case_of_assign():
    store = StateStore()
    store.apply(state("claude", "one", "TOOL"))
    assert store.assign(1, NOW)[0].session_id == store.active(NOW).session_id


def test_no_live_sessions_gives_every_slot_nothing():
    store = StateStore(active_ttl=10)
    store.apply(state("claude", "gone", "DONE"))
    assert store.assign(3, NOW + timedelta(seconds=11)) == [None, None, None]
    assert store.slots == [None, None, None]
    assert store.shown == {}


def test_fewer_live_sessions_than_slots_leaves_the_rest_empty():
    store = StateStore()
    store.apply(state("claude", "one", "TOOL"))
    assert ids(store.assign(3, NOW)) == ["one", None, None]


def test_each_session_gets_its_own_slot_with_no_duplicates():
    store = StateStore()
    for index, name in enumerate(("one", "two", "three")):
        store.apply(state("claude", name, "TOOL", index))
    shown = ids(store.assign(3, NOW + timedelta(seconds=3)))
    assert set(shown) == {"one", "two", "three"}
    assert len(set(shown)) == 3


def test_more_sessions_than_slots_shows_only_as_many_as_there_are_tiles():
    store = StateStore()
    for index, name in enumerate(("one", "two", "three", "four")):
        store.apply(state("claude", name, "TOOL", index))
    shown = ids(store.assign(2, NOW + timedelta(seconds=4)))
    assert len([entry for entry in shown if entry]) == 2
    assert len(set(shown)) == 2


def test_sessions_do_not_hop_between_slots_while_nothing_changes():
    """Two sessions, two tiles: nothing should ever move."""
    store = StateStore(switch_dwell=4.0)
    store.apply(state("claude", "one", "TOOL", 0))
    store.apply(state("codex", "two", "TOOL", 1))
    first = ids(store.assign(2, NOW + timedelta(seconds=1)))
    assert set(first) == {"one", "two"}
    for tick in range(2, 40):
        assert ids(store.assign(2, NOW + timedelta(seconds=tick))) == first


def test_a_session_keeps_its_own_slot_when_it_alone_keeps_working():
    store = StateStore(switch_dwell=4.0)
    store.apply(state("claude", "one", "TOOL", 0))
    store.apply(state("codex", "two", "TOOL", 0))
    first = ids(store.assign(2, NOW))
    quiet_slot = first.index("two")
    for tick in range(1, 30):
        store.apply(state("claude", "one", "TOOL", tick))
        assert ids(store.assign(2, NOW + timedelta(seconds=tick)))[quiet_slot] == "two"


def test_the_surplus_rotates_through_the_tiles():
    store = StateStore(switch_dwell=4.0)
    names = ("one", "two", "three")
    seen = set()
    frames = []
    for tick in range(30):
        for name in names:
            store.apply(state("claude", name, "TOOL", tick))
        frame = ids(store.assign(2, NOW + timedelta(seconds=tick)))
        occupied = [entry for entry in frame if entry]
        # Never the same session in two tiles at once.
        assert len(set(occupied)) == len(occupied)
        seen.update(occupied)
        frames.append(frame)
    assert seen == set(names), "a session never reached a tile"
    # Each tile holds its session long enough to read rather than flickering.
    for slot in range(2):
        column = [frame[slot] for frame in frames]
        switches = sum(
            1 for i in range(1, len(column)) if column[i] != column[i - 1]
        )
        assert switches <= len(column) / 4


def test_a_fresh_session_cannot_displace_a_tile_inside_the_dwell():
    store = StateStore(switch_dwell=30.0)
    store.apply(state("claude", "holding", "TOOL", 0))
    assert ids(store.assign(1, NOW)) == ["holding"]
    store.apply(state("claude", "eager", "TOOL", 1))
    assert ids(store.assign(1, NOW + timedelta(seconds=1))) == ["holding"]


def test_an_approval_displaces_the_longest_held_tile_not_always_the_first():
    store = StateStore(switch_dwell=0.0)
    store.apply(state("claude", "first", "TOOL", 0))
    assert ids(store.assign(2, NOW)) == ["first", None]
    store.apply(state("claude", "second", "TOOL", 1))
    assert ids(store.assign(2, NOW + timedelta(seconds=1))) == ["first", "second"]
    # Rotate slot 0, which makes slot 1 the longest-held tile.
    store.apply(state("claude", "third", "TOOL", 2))
    assert ids(store.assign(2, NOW + timedelta(seconds=2))) == ["third", "second"]
    store.apply(state("claude", "asking", "APPROVAL", 3))
    assert ids(store.assign(2, NOW + timedelta(seconds=3))) == ["third", "asking"]


def test_an_approval_takes_an_empty_tile_before_evicting_anyone():
    store = StateStore(switch_dwell=30.0)
    store.apply(state("claude", "working", "TOOL", 0))
    assert ids(store.assign(2, NOW)) == ["working", None]
    store.apply(state("claude", "asking", "APPROVAL", 1))
    assert ids(store.assign(2, NOW + timedelta(seconds=1))) == ["working", "asking"]


def test_two_approvals_can_hold_both_tiles():
    store = StateStore(switch_dwell=30.0)
    store.apply(state("claude", "one", "APPROVAL", 0))
    store.apply(state("codex", "two", "APPROVAL", 1))
    assert set(ids(store.assign(2, NOW + timedelta(seconds=1)))) == {"one", "two"}


def test_the_slot_count_can_change_between_calls():
    store = StateStore()
    for index, name in enumerate(("one", "two", "three")):
        store.apply(state("claude", name, "TOOL", index))
    assert len(store.assign(3, NOW + timedelta(seconds=3))) == 3
    assert len(store.assign(1, NOW + timedelta(seconds=4))) == 1
    assert len(store.slots) == 1
    assert len(store.assign(3, NOW + timedelta(seconds=5))) == 3


def test_a_session_that_ends_frees_its_tile_and_leaves_the_other_alone():
    store = StateStore()
    store.apply(state("claude", "one", "TOOL", 0))
    store.apply(state("codex", "two", "TOOL", 1))
    before = ids(store.assign(2, NOW + timedelta(seconds=1)))
    assert set(before) == {"one", "two"}
    ending = state("claude", "one", "DONE", 2)
    ending.ended = True
    store.apply(ending)
    after = ids(store.assign(2, NOW + timedelta(seconds=2)))
    assert after[before.index("two")] == "two"
    assert after[before.index("one")] is None
