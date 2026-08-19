# Sleep/resume LCD recovery

After an overnight Windows sleep, the installed daemon remains alive but the LCD no longer updates. Relaunching from the shortcut appears to do nothing.

Acceptance criteria:
- A long suspend/resume gap invalidates the old display handle and reconnects.
- Relaunching the shortcut asks an existing daemon to reconnect the LCD.
- Regression tests, documentation, and both 0.10.0 installers are current.
- Selecting the shipped TURZX USB panel in settings applies its 1920x462 profile instead of retaining an incompatible legacy canvas.
