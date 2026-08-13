from usb_lcd_dashboard.install import EVENTS_BY_PROVIDER, _merge_hooks
from usb_lcd_dashboard.normalize import PHASES


def merged(provider="claude", existing=None):
    settings = {"hooks": existing} if existing else {}
    _merge_hooks(settings, provider, "usb-lcd-dashboard")
    return settings["hooks"]


def test_every_installed_event_maps_to_a_phase():
    """An event we register but do not normalise would arrive and mean nothing."""
    for provider, events in EVENTS_BY_PROVIDER.items():
        for event in events:
            assert event in PHASES, f"{provider} installs {event} with no phase"


def test_the_notification_hook_is_installed():
    """NOTICE is what the crab widget alarms on besides APPROVAL.

    The phase was mapped in normalize.PHASES long before the hook was registered,
    so it existed but could never fire. This is the guard on that staying fixed.
    """
    assert "Notification" in EVENTS_BY_PROVIDER["claude"]
    assert "Notification" in EVENTS_BY_PROVIDER["codex"]
    assert PHASES["Notification"] == "NOTICE"
    hooks = merged()
    assert "Notification" in hooks
    command = hooks["Notification"][0]["hooks"][0]["command"]
    assert command == "usb-lcd-dashboard emit --provider claude"


def test_the_approval_hook_is_still_installed():
    assert "PermissionRequest" in merged()


def test_merging_preserves_someone_elses_hook():
    """The installer merges rather than replaces, which is what makes it safe to
    re-run to pick up a newly added event."""
    theirs = {
        "hooks": [{"type": "command", "command": "notify-send hello"}]
    }
    hooks = merged(existing={"Notification": [theirs]})
    commands = [
        entry["command"]
        for group in hooks["Notification"]
        for entry in group["hooks"]
    ]
    assert "notify-send hello" in commands
    assert "usb-lcd-dashboard emit --provider claude" in commands


def test_merging_twice_does_not_duplicate_our_hook():
    settings = {}
    _merge_hooks(settings, "claude", "usb-lcd-dashboard")
    _merge_hooks(settings, "claude", "usb-lcd-dashboard")
    ours = [
        entry
        for group in settings["hooks"]["Notification"]
        for entry in group["hooks"]
        if "usb-lcd-dashboard" in entry["command"]
    ]
    assert len(ours) == 1
