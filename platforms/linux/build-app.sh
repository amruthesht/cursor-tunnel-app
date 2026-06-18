#!/usr/bin/env bash
# Build standalone CursorTunnelApp binary for Linux (PyInstaller).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

find_python() {
  for cmd in python3.12 python3.11 python3 python; do
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
  echo "No suitable Python 3.10+ found." >&2
  exit 1
}

echo "Using Python: $PYTHON"
echo "Installing build deps..."
"$PYTHON" -m pip install -q -r requirements.txt pyinstaller

VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, 'app'); from version import __version__; print(__version__)")"
ARCH="$(uname -m)"
echo "Building CursorTunnelApp v$VERSION (Linux ${ARCH})..."
ICON="$ROOT/resources/icon.png"
ICON_ARGS=()
if [[ -f "$ICON" ]]; then
  ICON_ARGS=(--icon "$ICON")
fi

"$PYTHON" -m PyInstaller --noconfirm --onefile --name CursorTunnelApp "${ICON_ARGS[@]}" \
  --add-data "app/static:static" \
  --add-data "cluster:cluster" \
  --paths "app" \
  --hidden-import paramiko \
  app/main.py

BIN="$ROOT/dist/CursorTunnelApp"
if [[ ! -f "$BIN" ]]; then
  echo "Build finished but $BIN was not created" >&2
  exit 1
fi

chmod +x "$BIN"

ARCHIVE="$ROOT/dist/CursorTunnelApp-linux-${ARCH}.tar.gz"
rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" -C "$ROOT/dist" CursorTunnelApp

echo ""
echo "Done:"
echo "  $BIN"
echo "  $ARCHIVE"
echo ""
echo "Run: ./dist/CursorTunnelApp  (opens dashboard in your browser)"
