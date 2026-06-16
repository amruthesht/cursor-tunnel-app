#!/usr/bin/env bash
# Build Cursor Tunnel APK with Briefcase (Linux or WSL).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python 3 first: sudo apt install python3 python3-venv python3-pip" >&2
  exit 1
fi

VENV="$REPO_ROOT/.venv-android"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Installing Briefcase + deps..."
python -m pip install -U pip briefcase paramiko
python -m pip install -r requirements.txt

briefcase_args=()
if [[ "${CI:-}" == "true" ]]; then
  briefcase_args+=(--no-input)
  if [[ -n "${JAVA_HOME_17_X64:-}" ]]; then
    export JAVA_HOME="$JAVA_HOME_17_X64"
  elif [[ -n "${JAVA_HOME_17_arm64:-}" ]]; then
    export JAVA_HOME="$JAVA_HOME_17_arm64"
  fi
fi

android_project="$(find "$REPO_ROOT/build" -path '*/android/gradle' -type d 2>/dev/null | head -1 || true)"

if [[ -z "$android_project" ]]; then
  echo "First-time setup: briefcase create android (downloads SDK ~1 GB, can take 30+ min)"
  if [[ "${CI:-}" == "true" ]]; then
    yes | briefcase create android "${briefcase_args[@]}"
  else
    briefcase create android "${briefcase_args[@]}"
  fi
else
  echo "Updating Android project..."
  briefcase update android "${briefcase_args[@]}"
fi

briefcase build android "${briefcase_args[@]}"
briefcase package android -p apk "${briefcase_args[@]}"

RELEASE_APK="$REPO_ROOT/dist/CursorTunnelApp-android.apk"
mkdir -p "$REPO_ROOT/dist"
SOURCE_APK="$(find "$REPO_ROOT/dist" -maxdepth 1 -name '*.apk' -type f | head -1 || true)"
if [[ -z "$SOURCE_APK" ]]; then
  echo "No APK found under dist/" >&2
  exit 1
fi
cp "$SOURCE_APK" "$RELEASE_APK"
echo "Built $RELEASE_APK"
