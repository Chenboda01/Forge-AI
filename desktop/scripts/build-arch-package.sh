#!/usr/bin/env bash
#
# Build the native Arch package (forge-ai-desktop-bin) from the verified
# Forge AI Desktop .deb.
#
# The PKGBUILD pins the SHA-256 of the tested 1.1.0 artifact. This script
# verifies the input before handing it to makepkg so a stale or different build
# cannot be published under the same version.
#
# Requires: podman.
#
# Environment overrides:
#   FORGE_DEB          Input .deb (default: desktop/out/make/deb/x64/<name>)
#   FORGE_ARCH_IMAGE   Build image (default: archlinux:latest)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname -- "$SCRIPT_DIR")"
PKG_DIR="$DESKTOP_DIR/packaging/arch"
BUILD_DIR="$DESKTOP_DIR/.build/arch"
OUT_DIR="$DESKTOP_DIR/out/make/arch"
IMAGE="${FORGE_ARCH_IMAGE:-archlinux:latest}"

PKGBUILD="$PKG_DIR/PKGBUILD"
DEB="${FORGE_DEB:-$DESKTOP_DIR/out/make/deb/x64/forge-ai-desktop_1.1.0_amd64.deb}"

if ! command -v podman >/dev/null 2>&1; then
  echo "error: podman is required to build the Arch package." >&2
  exit 1
fi

if [ ! -f "$PKGBUILD" ]; then
  echo "error: missing $PKGBUILD" >&2
  exit 1
fi

if [ ! -f "$DEB" ]; then
  echo "error: Debian package not found: $DEB" >&2
  echo "       build installers first, or set FORGE_DEB." >&2
  exit 1
fi

expected="$(sed -n "s/^sha256sums=('\([0-9a-f]*\)')$/\1/p" "$PKGBUILD")"
actual="$(sha256sum "$DEB" | awk '{print $1}')"

if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
  echo "error: input does not match the checksum pinned in PKGBUILD." >&2
  echo "       expected: $expected" >&2
  echo "       actual:   $actual" >&2
  echo "       Use the artifact recorded in the release evidence snapshot." >&2
  exit 1
fi

rm -rf -- "$BUILD_DIR" 2>/dev/null || podman unshare rm -rf -- "$BUILD_DIR"
mkdir -p -- "$BUILD_DIR"
cp -- "$PKGBUILD" "$BUILD_DIR/PKGBUILD"
cp -- "$DEB" "$BUILD_DIR/$(basename "$DEB")"

echo "Building Arch package in $IMAGE..."

podman run --rm --network host \
  -v "$BUILD_DIR:/pkg" \
  "$IMAGE" \
  bash -c '
    set -euo pipefail
    pacman -Syu --noconfirm --needed base-devel libarchive >/dev/null
    useradd -m builder
    chown -R builder /pkg
    # Packaging only copies files, so runtime dependencies are not needed to
    # build; they are declared in the package and verified by the clean-install
    # test in test-arch-package.sh.
    su builder -c "cd /pkg && makepkg --noconfirm --cleanbuild --force --nodeps"
  '

mkdir -p -- "$OUT_DIR"
cp -- "$BUILD_DIR"/*.pkg.tar.zst "$OUT_DIR/"

echo
echo "Arch package written to $OUT_DIR:"
ls -l -- "$OUT_DIR"/*.pkg.tar.zst
