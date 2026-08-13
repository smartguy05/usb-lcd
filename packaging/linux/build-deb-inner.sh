#!/usr/bin/env bash
# The half of the build that runs inside the Ubuntu container. Split out from
# build-deb.sh so the container command stays a file rather than a quoted blob,
# which keeps it readable and lets shellcheck see it.
set -euo pipefail

: "${APP_VERSION:?}"
: "${SMARTSCREEN_COMMIT:?}"

# Built inside the container rather than on the bind mount: a Windows mount
# reports every directory as mode 777, and dpkg-deb refuses a control directory
# that is not between 0755 and 0775. Only the finished .deb crosses back.
BUILD_DIR=/tmp/build
CACHE_DIR="$BUILD_DIR/cache"
ROOT="$BUILD_DIR/root"                       # the package's filesystem tree
SITE="$ROOT/usr/lib/python3/dist-packages"   # where Debian puts python modules
DIST=/work/dist

export DEBIAN_FRONTEND=noninteractive
apt-get update >/dev/null
apt-get install -y --no-install-recommends \
    dpkg-dev fakeroot python3-pip python3-venv git ca-certificates >/dev/null

rm -rf "$ROOT"
mkdir -p "$CACHE_DIR" "$SITE" "$DIST"
mkdir -p "$ROOT/usr/bin" "$ROOT/lib/udev/rules.d" \
         "$ROOT/usr/share/doc/usb-lcd-dashboard" "$ROOT/DEBIAN"

# --- the dashboard itself -----------------------------------------------------
cp -R /work/src/usb_lcd_dashboard "$SITE/"

# --- smartscreen-driver, vendored --------------------------------------------
# Not in the Ubuntu archive. Pure Python and GPLv3, same licence as this
# project, so it ships inside the package rather than becoming a pip step that
# would need network at install time.
python3 -m pip wheel --no-deps --wheel-dir "$CACHE_DIR" \
    "smartscreen-driver @ git+https://github.com/hchargois/smartscreen-driver.git@${SMARTSCREEN_COMMIT}" \
    >/dev/null
WHEEL="$(ls "$CACHE_DIR"/smartscreen_driver-*.whl | head -1)"
python3 -m zipfile -e "$WHEEL" "$CACHE_DIR/smartscreen"
cp -R "$CACHE_DIR/smartscreen/smartscreen_driver" "$SITE/"
SMARTSCREEN_VERSION="$(basename "$WHEEL" | cut -d- -f2)"

find "$SITE" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$SITE" -type f -name '*.pyc' -delete

# --- the entry point ----------------------------------------------------------
# A real script rather than a shim: /usr/bin/usb-lcd-dashboard has to exist as a
# sibling of /usr/bin/python3, because install.py finds the command to put in
# the hooks and the systemd unit by looking exactly there.
cat > "$ROOT/usr/bin/usb-lcd-dashboard" <<'PY'
#!/usr/bin/python3
from usb_lcd_dashboard.cli import main

raise SystemExit(main())
PY
chmod 0755 "$ROOT/usr/bin/usb-lcd-dashboard"

# --- the udev rule ------------------------------------------------------------
# This is what creates /dev/turing-lcd — the default device on Linux — and what
# grants the logged-in user access to it. Without it the panel is root-only and
# the configured device does not exist.
install -m 0644 /work/packaging/99-turing-lcd.rules "$ROOT/lib/udev/rules.d/"

# --- documentation ------------------------------------------------------------
install -m 0644 /work/LINUX.md "$ROOT/usr/share/doc/usb-lcd-dashboard/README.Debian"
install -m 0644 /work/config.example.toml "$ROOT/usr/share/doc/usb-lcd-dashboard/"
gzip -9n -c /work/packaging/linux/changelog > \
    "$ROOT/usr/share/doc/usb-lcd-dashboard/changelog.Debian.gz"
sed "s/@SMARTSCREEN_VERSION@/$SMARTSCREEN_VERSION/" \
    /work/packaging/linux/copyright > "$ROOT/usr/share/doc/usb-lcd-dashboard/copyright"

# --- control files ------------------------------------------------------------
INSTALLED_SIZE="$(du -ks "$ROOT" | cut -f1)"
sed -e "s/@VERSION@/$APP_VERSION/" -e "s/@INSTALLED_SIZE@/$INSTALLED_SIZE/" \
    /work/packaging/linux/control > "$ROOT/DEBIAN/control"

# Carriage returns stripped regardless of how the checkout landed. dpkg runs
# these with /bin/sh, which takes a trailing CR as part of the command and
# fails. .gitattributes pins LF, but a zip download or a stray editor can still
# reintroduce one, and that failure would only surface on the user's machine at
# install time.
for script in postinst postrm; do
    sed 's/\r$//' "/work/packaging/linux/$script" > "$ROOT/DEBIAN/$script"
    chmod 0755 "$ROOT/DEBIAN/$script"
done

# Modes come from the umask and from the mount, so set the ones dpkg cares
# about explicitly rather than inheriting whatever the host gave us.
find "$ROOT" -type d -exec chmod 0755 {} +
find "$SITE" -type f -exec chmod 0644 {} +
chmod 0755 "$ROOT/usr/bin/usb-lcd-dashboard"

# --- build --------------------------------------------------------------------
# fakeroot so the files are owned by root:root inside the archive without the
# build itself needing to run as root.
DEB="$DIST/usb-lcd-dashboard_${APP_VERSION}_all.deb"
fakeroot dpkg-deb --build --root-owner-group "$ROOT" "$DEB" >/dev/null

echo "--- package ---"
dpkg-deb --info "$DEB" | sed -n '/Package:/,$p'
echo "--- contents ---"
dpkg-deb --contents "$DEB" | awk '{print $1, $6, $7, $8}' | sort -k2

chown "$HOST_UID:$HOST_GID" "$DEB" 2>/dev/null || true
