#!/usr/bin/env bash
#
# Build the Linux installers (deb, rpm, AppImage) inside ubuntu:22.04.
#
# Building on the host compiles node-pty against the host glibc, which may be
# newer than the target distributions and fails at runtime (for example a
# GLIBC_2.42 dependency on Ubuntu 22.04's glibc 2.35). Building in the target
# image keeps the native module and the PyInstaller payload portable.
#
# Requires: podman, and a payload built by build-forge-payload-container.sh.
#
# Environment overrides:
#   FORGE_BUILD_IMAGE   Build image (default: ubuntu:22.04)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname -- "$SCRIPT_DIR")"
REPO_DIR="$(dirname -- "$DESKTOP_DIR")"
IMAGE="${FORGE_BUILD_IMAGE:-ubuntu:22.04}"
STAGE_DIR="$DESKTOP_DIR/.build/installers-container"

if ! command -v podman >/dev/null 2>&1; then
  echo "error: podman is required to build installers in a container." >&2
  exit 1
fi

if [ ! -x "$DESKTOP_DIR/resources/forge/forge" ]; then
  echo "error: payload missing; run build-forge-payload-container.sh first." >&2
  exit 1
fi

rm -rf -- "$STAGE_DIR"
mkdir -p -- "$STAGE_DIR"

echo "Building deb, rpm and AppImage in $IMAGE..."

podman run --rm --network host \
  -v "$REPO_DIR:/src-ro:ro" \
  -v "$DESKTOP_DIR/resources/forge:/payload:ro" \
  -v "$STAGE_DIR:/artifacts" \
  "$IMAGE" \
  bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    APT_OPTS="-o Acquire::ForceIPv4=true -o Acquire::Retries=3
      -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20"

    sed -i \
      "s|http://archive.ubuntu.com/ubuntu|http://mirrors.edge.kernel.org/ubuntu|g;
       s|http://security.ubuntu.com/ubuntu|http://mirrors.edge.kernel.org/ubuntu|g" \
      /etc/apt/sources.list
    apt-get update -qq $APT_OPTS
    apt-get install -y -qq $APT_OPTS \
      curl ca-certificates xz-utils build-essential python3 dpkg fakeroot \
      squashfs-tools rpm >/dev/null

    cd /tmp
    file=$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt \
      | awk "/linux-x64\.tar\.xz$/ {print \$2; exit}")
    curl -fsSLO "https://nodejs.org/dist/latest-v22.x/$file"
    tar -xf "$file" -C /opt
    dir=$(basename "$file" .tar.xz)
    for b in node npm npx; do
      ln -sf "/opt/$dir/bin/$b" "/usr/local/bin/$b"
    done
    echo "node $(node --version) npm $(npm --version)"

    mkdir -p /build/desktop
    tar -C /src-ro/desktop \
      --exclude=node_modules --exclude=out --exclude=.vite \
      --exclude=.build --exclude=resources \
      -cf - . | tar -C /build/desktop -xf -
    mkdir -p /build/desktop/resources
    cp -a /payload /build/desktop/resources/forge

    cd /build/desktop
    npm ci --no-audit --no-fund
    npx electron-forge make --targets deb,rpm,AppImage

    cp out/make/deb/x64/*.deb \
       out/make/rpm/x64/*.rpm \
       out/make/AppImage/x64/*.AppImage \
       /artifacts/
    ls -lh /artifacts
  '

for kind in deb/x64:*.deb rpm/x64:*.rpm AppImage/x64:*.AppImage; do
  dir="${kind%%:*}"
  pattern="${kind#*:}"
  mkdir -p -- "$DESKTOP_DIR/out/make/$dir"
  rm -f -- "$DESKTOP_DIR/out/make/$dir"/$pattern
  cp -- "$STAGE_DIR"/$pattern "$DESKTOP_DIR/out/make/$dir/"
done
rm -rf -- "$STAGE_DIR"

echo
echo "Installers written to $DESKTOP_DIR/out/make:"
find "$DESKTOP_DIR/out/make" -type f \
  \( -name '*.deb' -o -name '*.rpm' -o -name '*.AppImage' \) \
  -printf '%s  %p\n' | sort -k2
