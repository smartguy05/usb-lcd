# Notes

- `pythonw.exe` hides bind failures, so a second shortcut launch previously looked like a no-op while the original daemon owned TCP port 45722.
- USB handles cannot be assumed valid across Windows suspend/resume; a monotonic loop gap is a portable recovery signal and also covers a long USB-stack stall.
- The status-line proxy regression used the POSIX-only `cat` command; mock the downstream process so exact-byte behavior is tested consistently on Windows and POSIX.
- Live log evidence showed reconnect was already retrying; it failed because the editor saved `turing_usb` with the Rev A `480x320` canvas while PID 0092 reports `1920x462`.
- Post-install verification: the served settings page contains the wide-profile fix; the sole daemon connected at USB 1CBE:0092 and wrote 1920x462 full frames.
- 2026-09-04 recurrence on the legacy panel: resume recovery worked at 07:23
  (`Long runtime pause`, COM10 open, 480x320 full frame), but the LCD later went
  black while Windows still reported `USB35INCHIPSV2`/COM10 as Started and the
  daemon continued receiving events. No write failure or silent serial-handle
  replacement was logged. A reconnect control at 07:41 reopened COM10, resent
  panel initialization, forced a full frame, and restored the display.
- `SerialPanel.health_check()` detects only driver replacement of
  `lcd.lcd_serial`; it cannot detect a panel-side screen/protocol reset that
  leaves the same Windows serial handle usable. Any automatic repair needs a
  reliable detector or a carefully bounded periodic reinitialization.
- In the managed Windows workspace, Python 3.13 pytest can report `WinError
  448` after otherwise-passing tests while resolving its `*_current` temp
  junction. Verification succeeded with a fresh explicit `--basetemp` and the
  pytest dead-symlink cleanup hook disabled; the dedicated temp trees were then
  removed explicitly.
