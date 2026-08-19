# Settings editor usability rework

Reorganise the admin settings editor (`admin_page.py`). The widget settings were
hard to use: nine anonymous `<section>`s stacked in a fixed 340px right rail
beside the canvas, so per-widget options were cramped and integration settings
sat far from the widget they feed.

## Acceptance criteria

- The live panel preview moves into a tab.
- A second tab holds widget settings for the selected tile. With no tile
  selected, show the first; with no tiles at all, show a message to add one.
- The tile canvas stays visible above the tabs — everything else is relative to
  a tile on it.
- Selected tile, background, screen saver and display settings leave the right
  rail for one collapsible panel.
- Dashboard, Discord, Windows notifications, todos and the read-only block move
  into the widget tab, shown contextually per selected widget.
- Presentation only: no new config keys, no change to the wire shape or the
  save payload.

## Decisions taken with the user

- Canvas always visible, above the tabstrip (not inside a tab).
- One collapsible **Settings** panel with sections Background / Screen saver /
  Display, in that order.
- Widget choice follows tile selection; no separate picker or sidebar.
- The whole selected-tile form (widget picker, geometry, options, delete) lives
  in the widget tab — so "Selected tile" is *not* one of the panel's sections.
- Source-backed blocks are contextual per widget, not always-on sections.
- Input polish accepted: colour swatches, human labels, numeric min/max/step.
