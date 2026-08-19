# Notes

- `pythonw.exe` hides bind failures, so a second shortcut launch previously looked like a no-op while the original daemon owned TCP port 45722.
- USB handles cannot be assumed valid across Windows suspend/resume; a monotonic loop gap is a portable recovery signal and also covers a long USB-stack stall.
- The status-line proxy regression used the POSIX-only `cat` command; mock the downstream process so exact-byte behavior is tested consistently on Windows and POSIX.
- Live log evidence showed reconnect was already retrying; it failed because the editor saved `turing_usb` with the Rev A `480x320` canvas while PID 0092 reports `1920x462`.
- Post-install verification: the served settings page contains the wide-profile fix; the sole daemon connected at USB 1CBE:0092 and wrote 1920x462 full frames.
