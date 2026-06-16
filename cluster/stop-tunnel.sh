#!/usr/bin/env bash
# Stop all cursor tunnel jobs for this user.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

user="${USER:-${LOGNAME:-}}"
prefix="${JOB_PREFIX:-cursor-tun-app}"

jobs="$(squeue -u "${user}" -h -o "%i %j" 2>/dev/null | awk -v p="${prefix}-" '$2 ~ p {print $1}' | tr '\n' ' ')"
if [[ -z "${jobs// /}" ]]; then
  echo "NONE"
  exit 0
fi
# shellcheck disable=SC2086
scancel ${jobs}
echo "${jobs}"
