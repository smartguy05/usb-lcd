# Todos — Linux parity

## Blocked on the user (needs sudo)
- [ ] Run scratchpad/setup-linux-parity.sh: apt deps + udev rule

## After that
- [ ] Restart the daemon against the venv, confirm the panel draws
- [ ] Confirm the tray icon appears on GNOME and its menu opens the editor
- [ ] Re-point the systemd unit: it still says
      ExecStart=/home/anthony/Code/usb-lcd/.venv/bin/usb-lcd-dashboard
      (written Jul 29). Phase 2 = /usr/bin after the .deb rebuild.

## Release artifacts (decision needed)
- [ ] Version bump? Still 0.10.0. Runtime code changed on BOTH platforms
      (tray.py, device.py, doctor.py, config.py), so dist/*.exe is stale too.
- [ ] Rebuild dist/usb-lcd-dashboard_<v>_all.deb (container build, can do here)
- [ ] Rebuild dist/USB-LCD-Dashboard-Setup-<v>.exe -- CANNOT do from Linux;
      CLAUDE.md requires Windows Git Bash + Windows SDK for the identity build.
- [ ] packaging/linux/changelog entry
- [ ] Update the sha256s quoted in README.md

## Deferred / worth considering
- [ ] `packaging/linux/smoke-test-inner.sh` only asserts the udev rule is gone
      after removal; nothing asserts the 1cbe line is present. Cheap to add.
- [ ] The tray's left-click-opens-settings is a request GNOME ignores (it opens
      the menu instead). Fine, but README now documents the difference.
