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

# Chaquopy's cryptography 42.0.8-0 wheels are 4 KB aligned; use 42.0.8-1 for Android 15+ phones.
CRYPTO_WHEEL_BASE="https://raw.githubusercontent.com/emanuele-f/chaquopy-wheels/master"
CRYPTO_WHEELS=(
  "cryptography-42.0.8-1-cp313-cp313-android_24_arm64_v8a.whl"
  "cryptography-42.0.8-1-cp313-cp313-android_24_x86_64.whl"
)
WHEELS_DIR="$REPO_ROOT/platforms/android/wheels"
mkdir -p "$WHEELS_DIR"
for wheel in "${CRYPTO_WHEELS[@]}"; do
  dest="$WHEELS_DIR/$wheel"
  if [[ "${CI:-}" == "true" || ! -f "$dest" ]]; then
    echo "Fetching $wheel (16 KB-aligned cryptography)..."
    curl -fsSL "$CRYPTO_WHEEL_BASE/$wheel" -o "$dest"
  fi
done

# Briefcase does not always bundle pyproject "resources"; copy cluster scripts into the app tree.
RESOURCE_CLUSTER="$REPO_ROOT/app/resources/cluster"
mkdir -p "$RESOURCE_CLUSTER"
cp -r "$REPO_ROOT/cluster/." "$RESOURCE_CLUSTER/"

android_project="$(find "$REPO_ROOT/build" -path '*/android/gradle' -type d 2>/dev/null | head -1 || true)"

if [[ -z "$android_project" ]]; then
  echo "First-time setup: briefcase create android (downloads SDK ~1 GB, can take 30+ min)"
  briefcase create android "${briefcase_args[@]}"
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

# Briefcase release APKs are unsigned; Android rejects them as invalid/corrupt.
find_apksigner() {
  local roots=() root bt
  [[ -n "${ANDROID_HOME:-}" ]] && roots+=("$ANDROID_HOME")
  [[ -n "${ANDROID_SDK_ROOT:-}" ]] && roots+=("$ANDROID_SDK_ROOT")
  roots+=("/usr/local/lib/android/sdk" "$HOME/.briefcase/tools/android_sdk")
  for root in "${roots[@]}"; do
    [[ -d "$root/build-tools" ]] || continue
    bt="$(find "$root/build-tools" -maxdepth 2 -name apksigner -type f 2>/dev/null | sort -V | tail -1 || true)"
    if [[ -n "$bt" ]]; then
      echo "$bt"
      return 0
    fi
  done
  return 1
}

CI_KEYSTORE="$REPO_ROOT/platforms/android/.ci-signing.jks"
CI_KS_PASS="${ANDROID_CI_KEYSTORE_PASSWORD:-android}"
CI_KEY_ALIAS="${ANDROID_CI_KEY_ALIAS:-upload}"
if [[ ! -f "$CI_KEYSTORE" ]]; then
  echo "Creating CI/dev signing keystore..."
  keytool -genkeypair -v \
    -keystore "$CI_KEYSTORE" -storepass "$CI_KS_PASS" -keypass "$CI_KS_PASS" \
    -alias "$CI_KEY_ALIAS" -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Cursor Tunnel CI, OU=Dev, O=Cursor Tunnel, L=NA, ST=NA, C=US"
fi

APKSIGNER="$(find_apksigner)" || {
  echo "ERROR: apksigner not found (need Android SDK build-tools)" >&2
  exit 1
}
SIGNED_APK="${RELEASE_APK}.signed"
"$APKSIGNER" sign --ks "$CI_KEYSTORE" --ks-pass "pass:$CI_KS_PASS" \
  --key-pass "pass:$CI_KS_PASS" --out "$SIGNED_APK" "$RELEASE_APK"
mv "$SIGNED_APK" "$RELEASE_APK"
echo "Signed $RELEASE_APK"

python "$SCRIPT_DIR/verify-apk-16k.py" "$RELEASE_APK"
python "$SCRIPT_DIR/verify-apk-bundle.py" "$RELEASE_APK"
