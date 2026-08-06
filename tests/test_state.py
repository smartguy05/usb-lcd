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
