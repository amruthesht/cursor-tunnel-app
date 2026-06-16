#!/usr/bin/env bash
# Shared helpers for remote cluster scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/config.env" ]]; then
  # shellcheck source=config.env
  source "${SCRIPT_DIR}/config.env"
else
  echo "Missing ${SCRIPT_DIR}/config.env" >&2
  exit 1
fi

: "${TUNNEL_AUTH_PROVIDER:=github}"
: "${JOB_PREFIX:=cursor-tun-app}"

CURSOR_TUNNEL_HOME="${CURSOR_TUNNEL_HOME:-${SCRIPT_DIR}}"
CPUS="${CPUS:-4}"
MEM="${MEM:-8G}"
TIME="${TIME:-04:00:00}"
CURSOR_BIN="${CURSOR_BIN:-${CURSOR_TUNNEL_HOME}/cursor}"

slurm_job_name_for_tunnel() {
  local safe
  safe="$(echo "$1" | tr -c 'A-Za-z0-9._-' '_' | sed -e 's/^_\+//' -e 's/_\+$//' -e 's/__\+/_/g')"
  # Slurm job names max 24 chars — use short prefix ct-
  printf 'ct-%s' "$(echo "${safe}" | cut -c1-21)"
}

slurm_extra_args() {
  local args=()
  [[ -n "${SLURM_PARTITION:-}" ]] && args+=(-p "${SLURM_PARTITION}")
  [[ -n "${SLURM_ACCOUNT:-}" ]] && args+=(-A "${SLURM_ACCOUNT}")
  [[ -n "${SLURM_QOS:-}" ]] && args+=("--qos=${SLURM_QOS}")
  printf '%s\n' "${args[@]}"
}
