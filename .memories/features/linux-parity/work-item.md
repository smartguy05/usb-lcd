# Feature: Linux parity — new TURZX panel + system tray

## Goal
The app should behave the same on Linux as on Windows:
1. A system tray icon, clickable to open the settings editor.
2. Drive the user's *new* panel (TURZX 1CBE:0092, 1920x462).

## Environment (Anthony-Desktop, Ubuntu, GNOME/Wayland)
- Panel present: `1cbe:0092 TURZX1.0`, mfr TURZX, serial 551b0c93448e4703
- Vendor class `ff`, **no kernel driver bound** -> libusb, not a tty
- Sits behind: Genesys hub -> AV Access iDock -> Terminus hub (re-enumerates often)
- `org.kde.StatusNotifierWatcher` IS on the session bus -> SNI tray will show

## Acceptance
- [ ] Tray icon appears on GNOME, left-click opens settings
- [ ] Panel drawn at 1920x462 over native USB
- [ ] `doctor` reports the USB panel, not "waiting for 1a86:5722"
- [ ] .deb ships deps + udev rule so a clean install works
