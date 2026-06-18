#!/usr/bin/env bash
# Build CursorTunnelApp.app for macOS (PyInstaller).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

find_python() {
  for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      if "$cmd" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(find_python)" || {
  echo "No suitable Python 3.10+ found. Install from https://www.python.org/downloads/macos/" >&2
  exit 1
}

echo "Using Python: $PYTHON"
echo "Installing build deps..."
"$PYTHON" -m pip install -q -r requirements.txt pyinstaller

VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, 'app'); from version import __version__; print(__version__)")"
echo "Building CursorTunnelApp.app v$VERSION (macOS)..."
ICON="$ROOT/resources/icon.png"
ICON_ARGS=()
if [[ -f "$ICON" ]]; then
  ICON_ARGS=(--icon "$ICON")
fi

"$PYTHON" -m PyInstaller --noconfirm --windowed --name CursorTunnelApp "${ICON_ARGS[@]}" \
  --add-data "app/static:static" \
  --add-data "cluster:cluster" \
  --paths "app" \
  --hidden-import paramiko \
  app/main.py

APP="$ROOT/dist/CursorTunnelApp.app"
if [[ ! -d "$APP" ]]; then
  echo "Build finished but $APP was not created" >&2
  exit 1
fi

ZIP="$ROOT/dist/CursorTunnelApp-macos-arm64.zip"
rm -f "$ZIP"
(
  cd "$ROOT/dist"
  zip -qr "$(basename "$ZIP")" CursorTunnelApp.app
)

echo ""
echo "Done:"
echo "  $APP"
echo "  $ZIP"
echo ""
echo "First launch: unzip, move CursorTunnelApp.app to Applications, then right-click → Open if macOS blocks it."
