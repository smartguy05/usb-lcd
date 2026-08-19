# Todos

- [ ] **Rebuild the Windows installer.** `dist/USB-LCD-Dashboard-Setup-0.10.0.exe`
      is stale — the tree is at 0.11.0 and `README.md:425` still says
      _(rebuild on Windows for 0.11.0)_. Must be built from Windows Git Bash
      with the Windows SDK; cannot be produced on the Linux host.
- [ ] The host still runs the pre-rework 0.11.0 package. `sudo apt install
      ./dist/usb-lcd-dashboard_0.11.0_all.deb` to pick up the new editor.
- [ ] `claude_limits` is the one widget with no contextual settings block. If
      Claude usage limits ever grow settings, `wants_claude_limits` is the hook
      already in `showContextSections()`.
- [ ] `RANGES` and `LABELS` live in the JS because `Option` has only
      `type`/`default`/`help`. If the registry ever gains a `label` or range,
      move them and update `tests/test_admin.py:243` and `tests/test_widgets.py:60`.

## Deliberately not done

- Widget add/remove was left as-is: the user chose "presentation only".
