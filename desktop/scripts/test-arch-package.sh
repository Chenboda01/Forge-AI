#!/usr/bin/env bash
#
# Install the built Arch package in a clean archlinux container and verify the
# file layout, dependencies, launcher entry, and icons.
#
# Requires: podman.
#
# Environment overrides:
#   FORGE_PKG          Package to test (default: newest in out/make/arch)
#   FORGE_ARCH_IMAGE   Test image (default: archlinux:latest)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname -- "$SCRIPT_DIR")"
IMAGE="${FORGE_ARCH_IMAGE:-archlinux:latest}"

if [ -n "${FORGE_PKG:-}" ]; then
  PKG="$FORGE_PKG"
else
  PKG="$(find "$DESKTOP_DIR/out/make/arch" -name '*.pkg.tar.zst' -printf '%T@ %p\n' 2>/dev/null |
    sort -n | tail -1 | cut -d' ' -f2-)"
fi

if [ -z "${PKG:-}" ] || [ ! -f "$PKG" ]; then
  echo "error: Arch package not found; run build-arch-package.sh first." >&2
  exit 1
fi

echo "Testing $(basename "$PKG") in $IMAGE..."

podman run --rm --network host \
  -v "$PKG:/pkg/forge-ai-desktop.pkg.tar.zst:ro" \
  "$IMAGE" \
  bash -c '
    set -euo pipefail
    pacman -Syu --noconfirm --needed desktop-file-utils >/dev/null
    pacman -U --noconfirm /pkg/forge-ai-desktop.pkg.tar.zst >/dev/null

    pacman -Q forge-ai-desktop-bin
    test -x /opt/forge-ai-desktop/forge-ai-desktop
    test -L /usr/bin/forge-ai-desktop
    test -f /usr/share/applications/forge-ai-desktop.desktop
    test -f /usr/share/licenses/forge-ai-desktop-bin/LICENSE

    for size in 16 24 32 48 64 128 256 512; do
      test -f "/usr/share/icons/hicolor/${size}x${size}/apps/forge-ai-desktop.png"
    done
    echo "icons: ok"

    mode="$(stat -c "%a" /opt/forge-ai-desktop/chrome-sandbox)"
    test "$mode" = "4755"
    echo "chrome-sandbox mode: $mode"

    desktop-file-validate /usr/share/applications/forge-ai-desktop.desktop
    echo "desktop entry: ok"

    if ldd /opt/forge-ai-desktop/forge-ai-desktop | grep -q "not found"; then
      echo "missing shared libraries:" >&2
      ldd /opt/forge-ai-desktop/forge-ai-desktop | grep "not found" >&2
      exit 1
    fi
    echo "shared libraries: ok"

    if [ -d /usr/share/icons/hicolor ]; then
      gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi

    echo "package files:"
    pacman -Ql forge-ai-desktop-bin | awk "NR <= 12 {print \$2}"
    echo "arch package test: PASS"
  '
