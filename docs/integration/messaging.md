# Messaging and notification sources

> **Covers:** `src/usb_lcd_dashboard/discord.py`, `src/usb_lcd_dashboard/messaging.py`, `src/usb_lcd_dashboard/notifications.py`, `src/usb_lcd_dashboard/teams.py`

Both integrations do network or operating-system work outside rendering and
publish immutable snapshots to the daemon. Widgets only read those snapshots,
so a slow or unavailable provider cannot block frame composition.

`discord.py` owns the bot connection, selected-channel filtering, protected
token storage, and the local new-message count. It produces the provider-neutral
`MessageSnapshot` types from `messaging.py`. `teams.py` is the retained legacy
Microsoft Teams implementation and is not wired into the current daemon.

`notifications.py` is Windows-only at its platform boundary. Its public models
and literal filter logic remain importable everywhere, while the worker imports
PyWinRT only on Windows. It enumerates current toast notifications, identifies
apps by AUMID, applies app/include/exclude filters, and publishes newest-first
items for the rotating notification widget. Notification text is memory-only;
the dashboard never dismisses the Windows notification.

Windows access requires the signed external-location identity package described
in [../packaging/windows.md](../packaging/windows.md). The settings editor owns
the explicit access request and app selection.
