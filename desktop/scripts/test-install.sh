#!/usr/bin/env bash
#
# Verify built installers in clean containers. Requires podman and artifacts
# produced by `npm run make`.
set -euo pipefail

DESKTOP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MAKE_DIR="$DESKTOP_DIR/out/make"

artifact() {
  local pattern="$1"
  local path

  path="$(find "$MAKE_DIR" -type f -name "$pattern" | head -1)"

  if [ -z "$path" ]; then
    echo "error: no $pattern under $MAKE_DIR; run 'npm run make' first" >&2
    exit 1
  fi

  printf '%s\n' "$path"
}

# Shared assertions. Each container installs the package, launches the app
# under Xvfb as a non-root user, and confirms the bundled engine is the
# process that actually runs. App logs must not show a native-module failure.
read -r -d '' CHECK_SCRIPT <<'CHECK' || true
set -euo pipefail
cd /tmp
(xvfb-run -a "$APP" --no-sandbox --disable-gpu >/tmp/app.log 2>&1 &)
sleep 20
pid="$(pgrep -x forge | head -1 || true)"
if [ -z "$pid" ]; then
  echo "error: bundled engine did not start" >&2
  tail -20 /tmp/app.log >&2
  exit 1
fi
exe="$(readlink -f "/proc/$pid/exe")"
case "$exe" in
  "$EXPECTED_PREFIX"*) ;;
  *)
    echo "error: unexpected engine executable: $exe" >&2
    exit 1
    ;;
esac
echo "bundled engine running: $exe"
if grep -qi 'loadNativeModule' /tmp/app.log; then
  echo "error: node-pty failed to load" >&2
  exit 1
fi
echo "node-pty loaded successfully"
CHECK

run_deb() {
  local deb
  deb="$(artifact '*.deb')"

  echo "== deb ($deb) in ubuntu:22.04 =="

  podman run --rm --network host \
    -v "$deb:/pkg/package.deb:ro" \
    -e APP=/usr/lib/forge-ai-desktop/forge-ai-desktop \
    -e EXPECTED_PREFIX=/usr/lib/forge-ai-desktop/resources/forge/forge \
    -e CHECK_SCRIPT="$CHECK_SCRIPT" \
    -e HOME=/home/tester \
    ubuntu:22.04 \
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
      apt-get install -y -qq $APT_OPTS xvfb xauth >/dev/null
      apt-get install -y $APT_OPTS /pkg/package.deb >/dev/null
      useradd -m tester
      su -m tester -s /bin/bash -c "$CHECK_SCRIPT"
    '
}

run_rpm() {
  local rpm
  rpm="$(artifact '*.rpm')"

  echo "== rpm ($rpm) in fedora:41 =="

  podman run --rm --network host \
    -v "$rpm:/pkg/package.rpm:ro" \
    -e APP=/usr/lib/forge-ai-desktop/forge-ai-desktop \
    -e EXPECTED_PREFIX=/usr/lib/forge-ai-desktop/resources/forge/forge \
    -e CHECK_SCRIPT="$CHECK_SCRIPT" \
    -e HOME=/home/tester \
    fedora:41 \
    bash -c '
      set -euo pipefail
      dnf -y --setopt=timeout=30 --setopt=retries=3 install \
        /pkg/package.rpm xorg-x11-server-Xvfb xauth procps-ng >/dev/null
      useradd -m tester
      su -m tester -s /bin/bash -c "$CHECK_SCRIPT"
    '
}

run_appimage() {
  local appimage
  appimage="$(artifact '*.AppImage')"

  echo "== AppImage ($appimage) in ubuntu:22.04 =="

  podman run --rm --network host \
    -v "$appimage:/pkg/package.AppImage:ro" \
    -e APP=/tmp/squashfs-root/AppRun \
    -e EXPECTED_PREFIX=/tmp/squashfs-root/usr/lib/forge-ai-desktop/resources/forge/forge \
    -e CHECK_SCRIPT="$CHECK_SCRIPT" \
    -e HOME=/home/tester \
    ubuntu:22.04 \
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
      apt-get install -y -qq $APT_OPTS xvfb xauth \
        libgtk-3-0 libnotify4 libnss3 xdg-utils libatspi2.0-0 libdrm2 \
        libgbm1 libxcb-dri3-0 libsecret-1-0 libglib2.0-bin libasound2 \
        >/dev/null
      cp /pkg/package.AppImage /tmp/app.AppImage
      chmod 755 /tmp/app.AppImage
      useradd -m tester
      su -m tester -s /bin/bash -c "
        cd /tmp
        ./app.AppImage --appimage-extract >/dev/null
        $CHECK_SCRIPT
      "
    '
}

run_deb
run_rpm
run_appimage

echo "all installer checks passed"
