# Device profiles

Automatically detect the attached supported LCD and use a separately saved
configuration for that physical panel, so one laptop can move between a legacy
480x320 serial display and a TURZX native-USB display without manual edits.

## Acceptance criteria

- Hardware detection, not configured canvas size, chooses the active panel.
- Each supported panel identity retains its own display, layout, and widget settings.
- Disconnecting one panel and attaching the other switches profiles automatically.
- Existing single-file configurations migrate without losing the current layout.
- The editor reads and saves the active device profile.
- Tests, documentation, release metadata, and both installers are current.
