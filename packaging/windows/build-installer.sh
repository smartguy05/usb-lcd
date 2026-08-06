#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$PROJECT_DIR/.build/windows"
CACHE_DIR="$BUILD_DIR/cache"
PAYLOAD_DIR="$PROJECT_DIR/packaging/windows/payload"
SITE_DIR="$PAYLOAD_DIR/Lib/site-packages"
DIST_DIR="$PROJECT_DIR/dist"
PYTHON_VERSION="3.12.10"
PYTHON_ARCHIVE="python-${PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_ARCHIVE}"
PYTHON_SHA256="4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
PILLOW_VERSION="12.3.0"
PY_SERIAL_VERSION="3.5"
NUMPY_VERSION="2.5.1"
SMARTSCREEN_COMMIT="918342ecbf33d210d41867f083142e3b5cbffcca"

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    HOST_PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    HOST_PYTHON="python3"
fi

for required in curl docker sha256sum; do
    if ! command -v "$required" >/dev/null; then
        echo "Missing required build command: $required" >&2
        exit 1
    fi
done

case "$BUILD_DIR" in
    "$PROJECT_DIR"/.build/windows) ;;
    *) echo "Refusing unexpected build directory: $BUILD_DIR" >&2; exit 1 ;;
esac
case "$PAYLOAD_DIR" in
    "$PROJECT_DIR"/packaging/windows/payload) ;;
    *) echo "Refusing unexpected payload directory: $PAYLOAD_DIR" >&2; exit 1 ;;
esac

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
if [[ -d "$PAYLOAD_DIR" ]]; then
    docker run --rm \
        --volume "$PROJECT_DIR:/work" \
        ubuntu:24.04 \
        chown -R "$HOST_UID:$HOST_GID" /work/packaging/windows/payload
fi

rm -rf "$BUILD_DIR" "$PAYLOAD_DIR"
mkdir -p "$CACHE_DIR" "$SITE_DIR" "$DIST_DIR"

curl --fail --location --retry 3 --output "$CACHE_DIR/$PYTHON_ARCHIVE" "$PYTHON_URL"
printf '%s  %s\n' "$PYTHON_SHA256" "$CACHE_DIR/$PYTHON_ARCHIVE" | sha256sum --check --status
"$HOST_PYTHON" -m zipfile -e "$CACHE_DIR/$PYTHON_ARCHIVE" "$PAYLOAD_DIR"

"$HOST_PYTHON" -m pip download \
    --dest "$CACHE_DIR" \
    --platform win_amd64 \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    --only-binary=:all: \
    "Pillow==$PILLOW_VERSION" \
    "pyserial==$PY_SERIAL_VERSION" \
    "numpy==$NUMPY_VERSION"
"$HOST_PYTHON" -m pip wheel \
    --no-deps \
    --wheel-dir "$CACHE_DIR" \
    "smartscreen-driver @ git+https://github.com/hchargois/smartscreen-driver.git@$SMARTSCREEN_COMMIT"

for wheel in "$CACHE_DIR"/*.whl; do
    "$HOST_PYTHON" -m zipfile -e "$wheel" "$SITE_DIR"
done

cp -R "$PROJECT_DIR/src/usb_lcd_dashboard" "$SITE_DIR/"
find "$SITE_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$SITE_DIR" -type f -name '*.pyc' -delete
cp "$PROJECT_DIR/LICENSE" "$PAYLOAD_DIR/LICENSE-USB-LCD-Dashboard.txt"
cp "$PROJECT_DIR/WINDOWS.md" "$PAYLOAD_DIR/README-Windows.txt"

PTH_FILE="$PAYLOAD_DIR/python312._pth"
sed -i '/^\.$/a Lib/site-packages' "$PTH_FILE"
sed -i 's/^#import site/import site/' "$PTH_FILE"

docker run --rm \
    --env HOST_UID="$HOST_UID" \
    --env HOST_GID="$HOST_GID" \
    --volume "$PROJECT_DIR:/work" \
    --workdir /work \
    ubuntu:24.04 \
    bash -lc 'apt-get update >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y nsis >/dev/null && makensis packaging/windows/installer.nsi && chown "$HOST_UID:$HOST_GID" dist/USB-LCD-Dashboard-Setup-0.2.2.exe'

INSTALLER="$DIST_DIR/USB-LCD-Dashboard-Setup-0.2.2.exe"
test -s "$INSTALLER"
file "$INSTALLER"
sha256sum "$INSTALLER"
echo "Windows installer ready: $INSTALLER"
