#!/usr/bin/env bash
# Copy resources/*.png into the Briefcase Android Gradle res tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RES="$REPO_ROOT/resources"

GRADLE_RES="$(find "$REPO_ROOT/build" -path '*/android/gradle/app/src/main/res' -type d 2>/dev/null | head -1 || true)"
if [[ -z "$GRADLE_RES" ]]; then
  echo "ERROR: Android Gradle res/ directory not found under build/" >&2
  exit 1
fi

copy() {
  local src="$1" dest="$2"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: missing icon source $src" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
}

# Launcher (square / round / adaptive) + splash — paths match Briefcase's Android template.
copy "$RES/square-icon-48.png"   "$GRADLE_RES/mipmap-mdpi/ic_launcher.png"
copy "$RES/square-icon-72.png"   "$GRADLE_RES/mipmap-hdpi/ic_launcher.png"
copy "$RES/square-icon-96.png"   "$GRADLE_RES/mipmap-xhdpi/ic_launcher.png"
copy "$RES/square-icon-144.png"  "$GRADLE_RES/mipmap-xxhdpi/ic_launcher.png"
copy "$RES/square-icon-192.png"  "$GRADLE_RES/mipmap-xxxhdpi/ic_launcher.png"

copy "$RES/round-icon-48.png"    "$GRADLE_RES/mipmap-mdpi/ic_launcher_round.png"
copy "$RES/round-icon-72.png"    "$GRADLE_RES/mipmap-hdpi/ic_launcher_round.png"
copy "$RES/round-icon-96.png"    "$GRADLE_RES/mipmap-xhdpi/ic_launcher_round.png"
copy "$RES/round-icon-144.png"   "$GRADLE_RES/mipmap-xxhdpi/ic_launcher_round.png"
copy "$RES/round-icon-192.png"   "$GRADLE_RES/mipmap-xxxhdpi/ic_launcher_round.png"

copy "$RES/adaptive-icon-108.png"  "$GRADLE_RES/mipmap-mdpi/ic_launcher_foreground.png"
copy "$RES/adaptive-icon-162.png"  "$GRADLE_RES/mipmap-hdpi/ic_launcher_foreground.png"
copy "$RES/adaptive-icon-216.png"  "$GRADLE_RES/mipmap-xhdpi/ic_launcher_foreground.png"
copy "$RES/adaptive-icon-324.png"  "$GRADLE_RES/mipmap-xxhdpi/ic_launcher_foreground.png"
copy "$RES/adaptive-icon-432.png"  "$GRADLE_RES/mipmap-xxxhdpi/ic_launcher_foreground.png"

copy "$RES/square-icon-320.png"  "$GRADLE_RES/mipmap-mdpi/splash.png"
copy "$RES/square-icon-480.png"  "$GRADLE_RES/mipmap-hdpi/splash.png"
copy "$RES/square-icon-640.png"  "$GRADLE_RES/mipmap-xhdpi/splash.png"
copy "$RES/square-icon-960.png"  "$GRADLE_RES/mipmap-xxhdpi/splash.png"
copy "$RES/square-icon-1280.png" "$GRADLE_RES/mipmap-xxxhdpi/splash.png"

echo "OK: launcher icons installed under $GRADLE_RES"
