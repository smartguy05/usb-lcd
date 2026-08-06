# USB LCD Dashboard

A landscape 480×320 status dashboard for Claude Code and Codex, built for the
3.5-inch Turing/UsbMonitor display:

```text
USB 1a86:5722
product UsbMonitor
serial USB35INCHIPSV2
```

The program does not display prompts, responses, or transcript text. It shows
only lifecycle metadata such as provider, model, project, elapsed time,
permission requests, and context used when the CLI exposes it.

The headline is the same activity line the agent prints above its own spinner —
"Editing src/render.py", "Running the installer build" — rebuilt from the tool
name and tool input the hook delivers. That is more useful than a bare tool
name, and it means the display can show file paths, search patterns, and command
descriptions taken from the current tool call.

## Windows 11

Use the self-contained `dist/USB-LCD-Dashboard-Setup-0.3.1.exe` installer. It
bundles its own Python runtime and dependencies, auto-detects the display as a
Windows COM port, installs Claude Code and Codex hooks, and starts at user login.
See [WINDOWS.md](WINDOWS.md) for installation and diagnostics.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/usb-lcd-dashboard doctor
.venv/bin/usb-lcd-dashboard run --simulate
```

The simulator writes the current frame to `screencap.png`.

## Installation

The installer merges user-level Claude and Codex hooks, preserves the existing
Claude status line, and installs a systemd user unit:

```bash
.venv/bin/usb-lcd-dashboard install
```

USB access requires the included device-specific udev rule:

```bash
sudo install -m 0644 packaging/99-turing-lcd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty --attr-match=idVendor=1a86
```

Then enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now usb-lcd-dashboard.service
```

Use `usb-lcd-dashboard uninstall` to restore the backed-up CLI settings and
remove the user service/configuration created by the installer. The system udev
rule is intentionally left for explicit removal.

## Commands

- `run`: run the dashboard daemon.
- `doctor`: inspect configuration, USB identity, permissions, hooks, and service.
- `doctor --paint-test`: display a test frame on the physical LCD.
- `emit --provider claude|codex`: consume one hook JSON object from stdin.
- `statusline-proxy`: preserve a Claude status line while forwarding its JSON.
- `install` / `uninstall`: manage reversible user-level integration.

This project is GPL-3.0-or-later because its display dependency is GPL-3.0.

