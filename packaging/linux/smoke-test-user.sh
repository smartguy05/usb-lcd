#!/usr/bin/env bash
# The per-user half, run as an unprivileged user inside the container.
set -euo pipefail
step() { echo; echo "==== $* ===="; }
cd "$HOME"

step "usb-lcd-dashboard install"
usb-lcd-dashboard install

step "the hooks and the unit point at a real path"
COMMAND=$(python3 -c "import json,pathlib;print(json.load(open(pathlib.Path.home()/'.claude/settings.json'))['hooks']['Notification'][0]['hooks'][0]['command'])")
echo "hook command: $COMMAND"
test -x "${COMMAND%% *}" || { echo "FAIL: hook points at a non-executable"; exit 1; }
grep -q "^ExecStart=/usr/bin/usb-lcd-dashboard run$" "$HOME/.config/systemd/user/usb-lcd-dashboard.service"
echo "unit ExecStart ok"

step "render a frame through the real daemon"
cat > "$HOME/.config/usb-lcd-dashboard/config.toml" <<'EOF'
[display]
kind = "simulated"
device = "AUTO"
width = 480
height = 320
refresh_hz = 8.0

[ipc]
mode = "unix"

[admin]
enabled = false

[[tile]]
widget = "crab"
x = 0
y = 0
w = 480
h = 320
EOF
export XDG_RUNTIME_DIR="/tmp/rt-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR" "$HOME/run"
cd "$HOME/run"
usb-lcd-dashboard run --simulate >/tmp/daemon.log 2>&1 &
sleep 3
cat > /tmp/event.json <<'EOF'
{"hook_event_name":"PermissionRequest","session_id":"a","cwd":"/home/tester/myproject","tool_name":"Bash","tool_input":{"description":"delete the build directory"}}
EOF
usb-lcd-dashboard emit --provider claude < /tmp/event.json
sleep 3
usb-lcd-dashboard shutdown || true
sleep 1
test -s "$HOME/run/screencap.png" || { echo "FAIL: no frame rendered"; cat /tmp/daemon.log; exit 1; }
python3 -c "from PIL import Image; i=Image.open('$HOME/run/screencap.png'); print('frame', i.size, i.mode)"
cp "$HOME/run/screencap.png" /work/dist/linux-screencap.png 2>/dev/null || true

step "doctor"
usb-lcd-dashboard doctor || echo "(exit 1 expected: no panel is attached to a container)"

step "usb-lcd-dashboard uninstall"
usb-lcd-dashboard uninstall
test ! -f "$HOME/.config/systemd/user/usb-lcd-dashboard.service" || { echo "FAIL: unit survived"; exit 1; }
python3 - <<'PYEOF'
import json, pathlib
d = json.load(open(pathlib.Path.home() / ".claude/settings.json"))
left = [e for e, g in d.get("hooks", {}).items() if "usb-lcd" in json.dumps(g)]
assert not left, f"hooks left behind: {left}"
assert "usb-lcd" not in json.dumps(d.get("statusLine")), "status line not restored"
print("hooks removed and status line restored")
PYEOF
