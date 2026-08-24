# Notes

- Existing `display.kind = "auto"` is size-based, so it cannot support moving
  between differently sized panels; it selected the legacy serial transport for
  a stale 480x320 config even while Windows exposed a TURZX device.
- Windows retained the legacy display as `USB35INCHIPSV2` / COM10 and exposes the
  large display as TURZX native USB, providing stable profile keys.
- The editor previously treated `auto` as an alias for `turing_rev_a` and reset
  the canvas to 480x320. Auto profile mode must preserve the current layout.
