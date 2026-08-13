#!/usr/bin/env bash
# Install the built .deb into a throwaway Ubuntu container and drive the whole
# lifecycle: package install, per-user install, a rendered frame, doctor,
# per-user uninstall, package removal.
#
# The unit tests cover the code; this covers the packaging — that the declared
# dependencies are enough, that the hooks and the systemd unit point at a path
# that exists, and that uninstall really puts things back.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_VERSION="$(grep -m1 '^version = ' "$PROJECT_DIR/pyproject.toml" | cut -d'"' -f2)"
test -n "$APP_VERSION"
DEB="dist/usb-lcd-dashboard_${APP_VERSION}_all.deb"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"
UBUNTU_IMAGE="${UBUNTU_IMAGE:-ubuntu:24.04}"

if [[ ! -s "$PROJECT_DIR/$DEB" ]]; then
    echo "Build it first: packaging/linux/build-deb.sh" >&2
    exit 1
fi

# Git Bash rewrites arguments that look like absolute paths, which mangles the
# mount point and the in-container paths.
MOUNT_DIR="$PROJECT_DIR"
case "$(uname -s)" in
    MINGW*|MSYS*) MOUNT_DIR="$(cd "$PROJECT_DIR" && pwd -W)" ;;
esac

echo "Smoke testing $DEB on $UBUNTU_IMAGE"

MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" run --rm \
    --volume "$MOUNT_DIR:/work" \
    --env DEB="$DEB" \
    "$UBUNTU_IMAGE" \
    bash -euo pipefail /work/packaging/linux/smoke-test-inner.sh
