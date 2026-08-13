#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

step() { echo; echo "==== $* ===="; }

step "apt install the package"
apt-get update >/dev/null
# No `head` in the pipeline: under pipefail its early exit SIGPIPEs grep,
# which set -e then treats as a failed step.
apt-get install -y "/work/$DEB" 2>&1 | grep -cE "^Setting up" | xargs -I{} echo "{} packages configured"

step "the command and its imports resolve"
usb-lcd-dashboard --help >/dev/null && echo "CLI ok"
python3 -c "import usb_lcd_dashboard, smartscreen_driver; print('modules ok', usb_lcd_dashboard.__version__)"
python3 -c "from usb_lcd_dashboard.render import _font; p=getattr(_font(24,True),'path',None); print('font:', p or 'BITMAP FALLBACK'); assert p, 'no TrueType font'"

useradd -m tester
cp /work/packaging/linux/smoke-test-user.sh /tmp/user.sh
chmod +x /tmp/user.sh
su tester -c "bash /tmp/user.sh"

step "apt remove"
apt-get remove -y usb-lcd-dashboard >/dev/null 2>&1
# A filesystem check, not `command -v`: bash caches resolved command paths
# and would still report the one it just ran.
test ! -e /usr/bin/usb-lcd-dashboard || { echo "FAIL: command survived removal"; exit 1; }
test ! -f /lib/udev/rules.d/99-turing-lcd.rules || { echo "FAIL: udev rule survived"; exit 1; }
echo "package removed cleanly"

echo; echo "==== smoke test passed ===="
