#!/usr/bin/env bash
# Start Cursor Tunnel App from source (Linux).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/cursor-tunnel-app"
mkdir -p "$CONFIG_DIR"
LOG_FILE="$CONFIG_DIR/cursor-tunnel-app.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

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

dashboard_url() {
  local cfg="$CONFIG_DIR/config.json"
  local port=8765
  if [[ -f "$cfg" ]]; then
    port="$(
      python3 - <<'PY' "$cfg" 2>/dev/null || echo 8765
import json, sys
try:
    print(int(json.load(open(sys.argv[1])).get("listen_port") or 8765))
except Exception:
    print(8765)
PY
    )"
  fi
  echo "http://127.0.0.1:${port}/"
}

PYTHON="$(find_python)" || {
  echo "Python 3.10+ required. Install python3 and re-run." >&2
  exit 1
}

log "Cursor Tunnel App starting (Linux)..."
log "Using Python: $PYTHON"

"$PYTHON" -m pip install -q -r requirements.txt

pkill -f "app/main.py" 2>/dev/null || true

nohup "$PYTHON" app/main.py >>"$LOG_FILE" 2>&1 &
URL="$(dashboard_url)"
log "Cursor Tunnel App ready at $URL"

if command -v xdg-open >/dev/null 2>&1; then
  sleep 1
  xdg-open "$URL" >/dev/null 2>&1 || true
fi

echo "Dashboard: $URL"
echo "Log: $LOG_FILE"
