#!/usr/bin/env bash
#
# Build the Forge CLI payload inside a target-matching container.
#
# PyInstaller collects native libraries from the build environment. Building on
# a host with a newer glibc can bundle libraries that require symbols missing
# from the target distribution (for example GLIBC_ABI_DT_RELR, introduced in
# glibc 2.36), so the payload fails to start on Ubuntu 22.04 (glibc 2.35) even
# though it works on the build host. Building inside ubuntu:22.04 keeps the
# payload's native dependencies at the same glibc floor as the installers.
#
# Requirements: podman.
#
# Environment overrides:
#   FORGE_BUILD_IMAGE   Build image (default: ubuntu:22.04)
#   FORGE_PYINSTALLER   PyInstaller version to install (default: 6.22.3)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname -- "$SCRIPT_DIR")"
REPO_DIR="$(dirname -- "$DESKTOP_DIR")"
OUTPUT_DIR="$DESKTOP_DIR/resources/forge"
STAGE_DIR="$DESKTOP_DIR/.build/payload-container"
IMAGE="${FORGE_BUILD_IMAGE:-ubuntu:22.04}"
PYINSTALLER_VERSION="${FORGE_PYINSTALLER:-6.22.3}"

if ! command -v podman >/dev/null 2>&1; then
  echo "error: podman is required to build the payload in a container." >&2
  exit 1
fi

if [ ! -f "$REPO_DIR/pyproject.toml" ]; then
  echo "error: cannot locate pyproject.toml at $REPO_DIR" >&2
  exit 1
fi

rm -rf -- "$STAGE_DIR"
mkdir -p -- "$STAGE_DIR"

echo "Building Forge payload in $IMAGE (PyInstaller $PYINSTALLER_VERSION)..."

podman run --rm --network host \
  -v "$REPO_DIR:/src:ro" \
  -v "$STAGE_DIR:/out" \
  -e PYINSTALLER_VERSION="$PYINSTALLER_VERSION" \
  "$IMAGE" \
  bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    APT_OPTS="-o Acquire::ForceIPv4=true -o Acquire::Retries=3
      -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20"

    apt-get update -qq $APT_OPTS
    apt-get install -y -qq $APT_OPTS ca-certificates curl binutils >/dev/null

    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"

    mkdir -p /work/desktop
    tar -C /src --exclude="*/__pycache__" --exclude="*.pyc" -cf - \
      forge pyproject.toml uv.lock LICENSE README.md | tar -C /work -xf -
    tar -C /src/desktop -cf - scripts | tar -C /work/desktop -xf -

    cd /work
    # Pin the interpreter: the lockfile is universal, but wheels are not. The
    # newest managed Python may lack prebuilt wheels (e.g. tiktoken) and would
    # require a Rust toolchain to build from source.
    uv python install 3.13
    uv sync --frozen --python 3.13
    echo "payload python: $(.venv/bin/python --version)"
    uv pip install --python .venv/bin/python "pyinstaller==$PYINSTALLER_VERSION"

    FORGE_PYTHON_PROJECT=/work \
      bash /work/desktop/scripts/build-forge-payload.sh

    cp -a /work/desktop/resources/forge /out/forge
  '

if [ ! -x "$STAGE_DIR/forge/forge" ]; then
  echo "error: container build did not produce a payload at $STAGE_DIR/forge" >&2
  exit 1
fi

rm -rf -- "$OUTPUT_DIR"
mkdir -p -- "$DESKTOP_DIR/resources"
cp -a "$STAGE_DIR/forge" "$OUTPUT_DIR"
rm -rf -- "$STAGE_DIR"

echo
echo "Payload installed at $OUTPUT_DIR"
"$OUTPUT_DIR/forge" --version
