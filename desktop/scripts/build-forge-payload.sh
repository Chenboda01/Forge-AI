#!/usr/bin/env bash
#
# Build the self-contained Forge CLI payload that ships inside the desktop app.
#
# The output is a PyInstaller onedir bundle at resources/forge/ with the
# executable at resources/forge/forge. The Electron main process launches that
# executable inside a PTY; end users do not need Python or pip installed.
#
# Requirements:
#   - uv (or a project venv with pyinstaller already installed)
#   - the Forge Python project (pyproject.toml with the `forge` package)
#
# Environment overrides:
#   FORGE_PYTHON_PROJECT  Path to the Forge-AI project (auto-detected)
#   FORGE_PYTHON          Python interpreter to build with (default: project venv)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname -- "$SCRIPT_DIR")"
OUTPUT_DIR="$DESKTOP_DIR/resources/forge"
WORK_DIR="$DESKTOP_DIR/.build/pyinstaller"

PROJECT_DIR="${FORGE_PYTHON_PROJECT:-}"

if [ -z "$PROJECT_DIR" ]; then
  for candidate in "$DESKTOP_DIR/../Forge-AI" "$DESKTOP_DIR/.."; do
    if [ -f "$candidate/pyproject.toml" ]; then
      PROJECT_DIR="$(cd -- "$candidate" && pwd)"
      break
    fi
  done
fi

if [ -z "$PROJECT_DIR" ] || [ ! -f "$PROJECT_DIR/pyproject.toml" ]; then
  echo "error: cannot locate the Forge Python project." >&2
  echo "       set FORGE_PYTHON_PROJECT=/path/to/Forge-AI" >&2
  exit 1
fi

PYTHON="${FORGE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
  echo "error: Python interpreter not found at $PYTHON" >&2
  echo "       run 'uv sync' in $PROJECT_DIR first" >&2
  exit 1
fi

if ! "$PYTHON" -c "import forge" >/dev/null 2>&1; then
  echo "error: the 'forge' package is not importable with $PYTHON" >&2
  echo "       run 'uv sync' in $PROJECT_DIR first" >&2
  exit 1
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$PYTHON" pyinstaller
  else
    "$PYTHON" -m pip install pyinstaller
  fi
fi

rm -rf -- "$OUTPUT_DIR" "$WORK_DIR"
mkdir -p -- "$DESKTOP_DIR/resources" "$WORK_DIR"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name forge \
  --distpath "$DESKTOP_DIR/resources" \
  --workpath "$WORK_DIR" \
  --specpath "$WORK_DIR" \
  --paths "$PROJECT_DIR" \
  --collect-all litellm \
  --collect-all textual \
  --collect-all keyring \
  --collect-all tiktoken \
  --collect-all tiktoken_ext \
  --copy-metadata litellm \
  --copy-metadata textual \
  --copy-metadata keyring \
  --copy-metadata tiktoken \
  --copy-metadata rich \
  --copy-metadata typer \
  --copy-metadata pydantic \
  --copy-metadata pydantic-settings \
  --add-data "$PROJECT_DIR/forge/ui/app.tcss:forge/ui" \
  "$SCRIPT_DIR/forge_entry.py"

echo
echo "Forge payload built at $OUTPUT_DIR"
"$OUTPUT_DIR/forge" --version
