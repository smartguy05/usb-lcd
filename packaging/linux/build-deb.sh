#!/usr/bin/env bash
# Build the Ubuntu .deb, in a container, from any host.
#
# Unlike the Windows installer this does not bundle a Python runtime. Ubuntu
# 24.04 already ships everything the dashboard needs — python3 3.12, Pillow,
# pySerial and numpy — so the package declares them as dependencies and apt
# resolves them. The one exception is smartscreen-driver, which is not in the
# archive; it is pure Python and GPLv3 like this project, so it is vendored.
#
# The result is architecture-independent ("all"): there is no compiled code in
# either the dashboard or the vendored driver.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$PROJECT_DIR/.build/linux"
CACHE_DIR="$BUILD_DIR/cache"
DIST_DIR="$PROJECT_DIR/dist"
APP_VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$PROJECT_DIR/pyproject.toml")"
test -n "$APP_VERSION"
SMARTSCREEN_COMMIT="918342ecbf33d210d41867f083142e3b5cbffcca"
UBUNTU_IMAGE="${UBUNTU_IMAGE:-ubuntu:24.04}"

# Podman serves the Docker API, so the default works for either runtime.
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"

for required in "$CONTAINER_RUNTIME"; do
    if ! command -v "$required" >/dev/null; then
        echo "Missing required build command: $required" >&2
        exit 1
    fi
done

case "$BUILD_DIR" in
    "$PROJECT_DIR"/.build/linux) ;;
    *) echo "Refusing unexpected build directory: $BUILD_DIR" >&2; exit 1 ;;
esac

# Git Bash rewrites arguments that look like absolute paths, which mangles both
# the mount point and the paths inside the container command. Turn that off for
# container calls only.
MOUNT_DIR="$PROJECT_DIR"
case "$(uname -s)" in
    MINGW*|MSYS*) MOUNT_DIR="$(cd "$PROJECT_DIR" && pwd -W)" ;;
esac

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

if [[ -d "$BUILD_DIR" ]]; then
    # Reclaim files a previous containerised build left owned by root. Windows
    # mounts virtualise ownership, so failure here is not a build failure.
    MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" run --rm \
        --volume "$MOUNT_DIR:/work" "$UBUNTU_IMAGE" \
        chown -R "$HOST_UID:$HOST_GID" /work/.build/linux || true
fi

rm -rf "$BUILD_DIR"
mkdir -p "$CACHE_DIR" "$DIST_DIR"

echo "Building usb-lcd-dashboard ${APP_VERSION} for ${UBUNTU_IMAGE}"

MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" run --rm \
    --volume "$MOUNT_DIR:/work" \
    --workdir /work \
    --env APP_VERSION="$APP_VERSION" \
    --env SMARTSCREEN_COMMIT="$SMARTSCREEN_COMMIT" \
    --env HOST_UID="$HOST_UID" \
    --env HOST_GID="$HOST_GID" \
    "$UBUNTU_IMAGE" \
    bash -euo pipefail /work/packaging/linux/build-deb-inner.sh

DEB="$DIST_DIR/usb-lcd-dashboard_${APP_VERSION}_all.deb"
test -s "$DEB"
echo
echo "Ubuntu package ready: $DEB"
