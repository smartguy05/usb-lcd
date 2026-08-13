# Recipes

Copy-pasteable. Windows paths use `.venv/Scripts/`; Linux uses `.venv/bin/`.

## Development

```bash
python3 -m venv .venv
.venv/Scripts/pip install -e '.[test]'
.venv/Scripts/pytest                                   # 384 tests, ~13s
.venv/Scripts/pytest tests/test_state.py -x
.venv/Scripts/usb-lcd-dashboard doctor
.venv/Scripts/usb-lcd-dashboard run --simulate         # writes ./screencap.png
```

## Drive the simulator with a fake event

The whole real path — IPC, normalise, arbitrate, compose — with no hardware.

```bash
USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
  .venv/bin/usb-lcd-dashboard run --simulate &

echo '{"hook_event_name":"PreToolUse","session_id":"a","cwd":"'"$PWD"'",
       "tool_name":"Edit","tool_input":{"file_path":"src/layout.py"}}' \
  | USB_LCD_DASHBOARD_CONFIG=./config.example.wide.toml \
    .venv/bin/usb-lcd-dashboard emit --provider claude
```

Trigger the alarm instead:

```bash
echo '{"hook_event_name":"PermissionRequest","session_id":"a","cwd":"'"$PWD"'",
       "tool_name":"Bash","tool_input":{"description":"delete the build dir"}}' \
  | ... emit --provider claude
```

`USB_LCD_DASHBOARD_CONFIG` (`config.py:default_path`) is the only way to test
against a config other than the installed one.

> **Use a spare `ipc.port` and `admin.port`.** A live daemon may hold 45722 /
> 45723, and a test daemon without its own ports will either fail to bind or
> feed the user's real panel.

## See the frame that is actually on the panel

Needs a running daemon with the editor enabled. No hardware required.

```bash
curl -s -o frame.png http://127.0.0.1:45723/api/preview.png
curl -s http://127.0.0.1:45723/api/config   | python -m json.tool
curl -s http://127.0.0.1:45723/api/widgets  | python -m json.tool
```

## Stop a daemon

```bash
.venv/Scripts/usb-lcd-dashboard shutdown       # same path as SIGTERM and tray Quit
```

## Documentation indexes

```bash
python docs/tools/build_index.py               # rebuild after moving code
python docs/tools/search.py --check            # validate every cited line number
python docs/tools/search.py --symbol assign
python docs/tools/search.py --file crab.py
```

## Packaging

```bash
packaging/windows/build-installer.sh           # needs Docker or Podman
packaging/linux/build-deb.sh
packaging/linux/smoke-test.sh                  # after build-deb.sh
CONTAINER_RUNTIME=podman packaging/linux/build-deb.sh
```

> **Never run `dist\*.exe` to inspect it** — NSIS `/S` is a full install, not an
> extraction.

## Linux service

```bash
systemctl --user status usb-lcd-dashboard
journalctl --user -u usb-lcd-dashboard -f      # there is no log file on Linux
sudo loginctl enable-linger "$USER"            # keep it alive without a login
```

## See also

- [../integration/cli.md](../integration/cli.md) — every subcommand.
- [config-schema.md](config-schema.md)
