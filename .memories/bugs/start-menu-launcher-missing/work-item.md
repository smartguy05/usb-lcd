# Bug: no Start-menu shortcut starts the dashboard

Reported: 2026-09-03. "If I need to reboot the app, killing the tray works but
if I click the icon in the start menu the tray icon never comes back."

## Behaviour

Quitting from the tray icon stops the daemon cleanly. Relaunching from the app's
Start-menu folder never brings the tray icon back, and leaves no log entry.

## Acceptance

- The Start-menu folder contains a shortcut that starts the daemon.
- Quit -> relaunch from the Start menu restores the tray icon.
- A relaunch while a daemon is already running still requests a reconnect
  rather than failing on the busy IPC port.
