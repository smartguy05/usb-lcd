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
