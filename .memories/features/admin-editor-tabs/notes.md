# Notes

## Mount ids must exist in the DOM at parse time — always

Show/hide sections with `hidden`; never create or destroy the mount divs.
Three things break otherwise:

1. Listeners are bound at module level at the bottom of the script, including
   `$("todoHistory").addEventListener` — a missing id throws during parse and
   the whole page dies silently.
2. `drawTodoCreate()` does `$("todoCreate").innerHTML = ""` with no null guard,
   and `load()` calls it unconditionally.
3. `snap()` reads `$("snap").value` live on every pointermove during a drag.

## The daemon holds `PAGE` in memory

Editing `admin_page.py` does nothing to a running daemon — the config hot-reload
watches `config.toml`, not the source. Restart the daemon to see page changes.
Cost me a confusing round of "my fix didn't apply".

## `tests/test_admin.py` asserts nine exact substrings of `PAGE`

All inside `changeDisplayKind` and the display-kind `choice()` call, including
argument spacing: `'["turing_rev_a", "turing_usb", ...], changeDisplayKind'`.
Reflowing that call breaks tests with no semantic change. Renaming
`drawSideForms` → `drawPanels` *inside* those functions is safe; the call lines
are not asserted.

## `<input type=color>` paints as an empty white box in headless Chromium

The value is correct, only the render is wrong — which makes any screenshot
check useless. Fixed for real by putting the colour on a `.chip` span and laying
the native input over it at `opacity: 0`. Note the chequerboard is a
`background-image`, so it paints *over* `background-color` — a set colour has to
clear `backgroundImage` too, or every swatch looks unset.

## Colour options cannot be a bare colour input

`"transparent"` and `""` (meaning "fall back to the widget default") are both
legal values, and blanking the field deletes the key. The text box has to stay
the value of record; the swatch is only a convenience beside it.

## `syncTileNumbers()` used a document-wide `[data-rect]` selector

Fine while one copy of the geometry inputs existed, silently wrong the moment a
second appears. Scoped to `#tileForm`.

## pkill -f "run --simulate" also matches the bash wrapper running it

Kills your own shell (exit 144) and takes the restart command with it. Start the
replacement daemon in a separate call. The user's real daemon runs as plain
`usb-lcd-dashboard run`, so the `--simulate` pattern does not touch it — but
`packaging/linux/smoke-test.sh` does restart the host's systemd user service.
