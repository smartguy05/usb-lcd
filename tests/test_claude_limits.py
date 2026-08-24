import json
from datetime import datetime, timedelta, timezone

from usb_lcd_dashboard.claude_limits import (
    ClaudeLimitsIntegration,
    parse_fable,
    parse_usage,
    parse_window,
)

NOW = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)


def test_native_window_parsing_clamps_and_requires_a_reset():
    window = parse_window({"used_percentage": 140, "resets_at": NOW.timestamp() + 60}, "statusline", NOW)
    assert window is not None and window.used_percentage == 100
    assert parse_window({"used_percentage": 10}, "statusline", NOW) is None
    assert parse_window(
        {"used_percentage": "nan", "resets_at": NOW.timestamp() + 60},
        "statusline",
        NOW,
    ) is None


def test_fable_parser_accepts_direct_legacy_and_dynamic_scopes():
    direct = parse_fable({"seven_day_fable": {"utilization": 25, "resets_at": (NOW + timedelta(days=1)).isoformat()}}, NOW)
    legacy = parse_fable({"seven_day_overage_included": {"utilization": 30, "resets_at": (NOW + timedelta(days=1)).isoformat()}}, NOW)
    dynamic = parse_fable({"weekly_scoped": [{
        "scope": {"model": {"display_name": "Claude Fable 5"}},
        "utilization": 35,
        "resets_at": (NOW + timedelta(days=1)).isoformat(),
    }]}, NOW)
    assert [window.used_percentage for window in (direct, legacy, dynamic) if window] == [25, 30, 35]


def test_usage_parser_includes_session_weekly_and_fable():
    reset = (NOW + timedelta(days=1)).isoformat()
    snapshot = parse_usage({
        "five_hour": {"utilization": 36, "resets_at": reset},
        "seven_day": {"utilization": 42, "resets_at": reset},
        "seven_day_fable": {"utilization": 12, "resets_at": reset},
    }, NOW)
    assert snapshot.five_hour is not None and snapshot.five_hour.used_percentage == 36
    assert snapshot.seven_day is not None and snapshot.seven_day.used_percentage == 42
    assert snapshot.fable is not None and snapshot.fable.used_percentage == 12


def test_native_observation_persists_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr("usb_lcd_dashboard.claude_limits._account_uuid", lambda: "account-a")
    path = tmp_path / "limits.json"
    integration = ClaudeLimitsIntegration(path)
    integration.observe("claude", {"rate_limits": {
        "five_hour": {"used_percentage": 17, "resets_at": (NOW + timedelta(hours=4)).timestamp()},
        "seven_day": {"used_percentage": 74, "resets_at": (NOW + timedelta(days=2)).timestamp()},
    }})
    saved = json.loads(path.read_text())
    assert saved["account_uuid"] == "account-a"
    assert saved["five_hour"]["used_percentage"] == 17
    assert "accessToken" not in path.read_text()
    loaded = ClaudeLimitsIntegration(path).snapshot()
    assert loaded.seven_day is not None and loaded.seven_day.used_percentage == 74


def test_cache_is_ignored_after_account_switch(tmp_path, monkeypatch):
    path = tmp_path / "limits.json"
    path.write_text(json.dumps({"account_uuid": "old", "five_hour": {}}))
    monkeypatch.setattr("usb_lcd_dashboard.claude_limits._account_uuid", lambda: "new")
    assert ClaudeLimitsIntegration(path).snapshot().five_hour is None


def test_refresh_keeps_cached_fable_on_failure(tmp_path, monkeypatch):
    integration = ClaudeLimitsIntegration(tmp_path / "limits.json")
    existing = parse_window({"utilization": 50, "resets_at": (NOW + timedelta(days=1)).isoformat()}, "oauth", NOW)
    integration._snapshot = integration.snapshot().__class__(fable=existing, status="current")
    monkeypatch.setattr(integration, "_fetch_usage", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    integration._refresh()
    assert integration.snapshot().fable == existing
    assert "offline" in integration.snapshot().error


def test_refresh_keeps_cached_fable_when_response_omits_bucket(
    tmp_path, monkeypatch
):
    integration = ClaudeLimitsIntegration(tmp_path / "limits.json")
    existing = parse_window(
        {
            "utilization": 50,
            "resets_at": (NOW + timedelta(days=1)).isoformat(),
        },
        "oauth",
        NOW,
    )
    integration._snapshot = integration.snapshot().__class__(
        fable=existing, status="current"
    )
    monkeypatch.setattr(integration, "_fetch_usage", lambda: integration.snapshot().__class__())
    integration._refresh()
    assert integration.snapshot().fable == existing
    assert integration.snapshot().error == "Fable limit unavailable"


def test_refresh_updates_session_from_oauth_usage(tmp_path, monkeypatch):
    integration = ClaudeLimitsIntegration(tmp_path / "limits.json")
    stale = parse_window(
        {"utilization": 26, "resets_at": (NOW + timedelta(hours=1)).isoformat()},
        "statusline",
        NOW,
    )
    fresh = parse_window(
        {"utilization": 36, "resets_at": (NOW + timedelta(hours=1)).isoformat()},
        "oauth",
        NOW,
    )
    integration._snapshot = integration.snapshot().__class__(five_hour=stale)
    monkeypatch.setattr(
        integration,
        "_fetch_usage",
        lambda: integration.snapshot().__class__(five_hour=fresh),
    )
    integration._refresh()
    assert integration.snapshot().five_hour == fresh
