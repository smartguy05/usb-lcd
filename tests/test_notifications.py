from datetime import datetime, timedelta, timezone

from usb_lcd_dashboard.notifications import (
    NotificationItem,
    WindowsNotificationIntegration,
    filter_items,
)

NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)


def item(id, app="chat", title="Hello", body="Please review", minutes=0):
    return NotificationItem(id, app, app.title(), title, body, NOW + timedelta(minutes=minutes))


def test_filters_by_app_and_sorts_newest_first():
    assert filter_items([item(1), item(2, minutes=1), item(3, "mail")], ["chat"]) == (
        item(2, minutes=1), item(1)
    )


def test_include_is_any_match_and_exclude_wins():
    items = [item(1, body="urgent review"), item(2, body="urgent secret"), item(3, body="later")]
    assert filter_items(items, ["chat"], ["urgent", "today"], ["secret"]) == (items[0],)


def test_duplicate_windows_ids_are_removed_per_app():
    assert filter_items([item(1), item(1), item(1, "mail")], ["chat", "mail"]) == (
        item(1), item(1, "mail")
    )


def test_non_windows_integration_is_safe_and_reports_unsupported():
    integration = WindowsNotificationIntegration()
    integration.start()
    assert integration.snapshot().status in {"unsupported", "permission_required"}
    integration.stop()
