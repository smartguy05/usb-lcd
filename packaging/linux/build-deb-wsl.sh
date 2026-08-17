#!/usr/bin/env bash
# Offline fallback for Windows hosts with Ubuntu under WSL. Reuses the vendored
# smartscreen driver from the previous package and rebuilds everything else.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$PROJECT_DIR/pyproject.toml")"
BOOTSTRAP="${1:-$PROJECT_DIR/dist/usb-lcd-dashboard_0.6.1_all.deb}"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
ROOT="$BUILD/root"

dpkg-deb -x "$BOOTSTRAP" "$ROOT"
dpkg-deb -e "$BOOTSTRAP" "$ROOT/DEBIAN"
SITE="$ROOT/usr/lib/python3/dist-packages"
rm -rf "$SITE/usb_lcd_dashboard"
cp -a "$PROJECT_DIR/src/usb_lcd_dashboard" "$SITE/"
find "$SITE/usb_lcd_dashboard" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$SITE/usb_lcd_dashboard" -type f -name '*.pyc' -delete

DOC="$ROOT/usr/share/doc/usb-lcd-dashboard"
install -m 0644 "$PROJECT_DIR/LINUX.md" "$DOC/README.Debian"
install -m 0644 "$PROJECT_DIR/config.example.toml" "$DOC/config.example.toml"
gzip -9n -c "$PROJECT_DIR/packaging/linux/changelog" > "$DOC/changelog.Debian.gz"

SIZE="$(du -ks "$ROOT" | cut -f1)"
sed -e "s/@VERSION@/$VERSION/" -e "s/@INSTALLED_SIZE@/$SIZE/" \
    "$PROJECT_DIR/packaging/linux/control" > "$ROOT/DEBIAN/control"
for script in postinst postrm; do
    sed 's/\r$//' "$PROJECT_DIR/packaging/linux/$script" > "$ROOT/DEBIAN/$script"
    chmod 0755 "$ROOT/DEBIAN/$script"
done
find "$ROOT" -type d -exec chmod 0755 {} +
find "$SITE" -type f -exec chmod 0644 {} +
chmod 0755 "$ROOT/usr/bin/usb-lcd-dashboard"
chmod 0644 "$ROOT/lib/udev/rules.d/99-turing-lcd.rules" "$ROOT/DEBIAN/control"

OUTPUT="$PROJECT_DIR/dist/usb-lcd-dashboard_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$ROOT" "$OUTPUT" >/dev/null
dpkg-deb --info "$OUTPUT" | sed -n '/ Package:/,$p'
echo "Linux package ready: $OUTPUT"
