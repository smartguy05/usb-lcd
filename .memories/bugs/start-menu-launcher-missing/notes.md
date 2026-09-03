# Notes

## Root cause

`installer.nsi` created only three shortcuts: the launcher in `$SMSTARTUP`, plus
`Diagnostics` and `Uninstall` in `$SMPROGRAMS\USB LCD Dashboard`. The app's
Start-menu folder therefore had no way to start anything. Clicking `Diagnostics`
runs `python.exe -m usb_lcd_dashboard doctor`, which prints and exits.

Both the code and the docs already assumed the launcher existed:

- `cli.py:80` - "The Start-menu and Startup shortcuts are intentionally the
  same", wrapping `run` so a second launch becomes a reconnect request.
- `WINDOWS.md` (sleep/wake section) told the user to relaunch from the Start
  menu to force a reconnect.

Both were added by the `sleep-resume-reconnect` work item, which shipped the
behaviour and its documentation but never added the shortcut itself.

## Why it left no trace

File logging is wired up only for the `run` command (`cli.py:42-45`), so a
`doctor` launch writes nothing to `dashboard.log`. Under `pythonw.exe` there is
no console either. The absence of new log lines after a click is itself the
evidence that `run` never executed.

## Diagnosing this class of bug

`$SMSTARTUP` is a subdirectory of `$SMPROGRAMS` (`Start Menu\Programs\Startup`),
so Start-menu *search* does surface the working Startup shortcut while the app's
own Start-menu *folder* is a dead end. Ask which one was clicked, and resolve
both with `WScript.Shell.CreateShortcut` before believing either.
