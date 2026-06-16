#!/bin/bash
#SBATCH --output=%x-%j.out
#SBATCH --error=%x-%j.err

set -euo pipefail

: "${CURSOR_TUNNEL_HOME:?CURSOR_TUNNEL_HOME not set — redeploy scripts from the app}"
# shellcheck source=/dev/null
source "${CURSOR_TUNNEL_HOME}/config.env"

TUNNEL_NAME="${TUNNEL_NAME_OVERRIDE:-${TUNNEL_NAME:-}}"
: "${TUNNEL_NAME:?Pass --tunnel-name when submitting}"

CURSOR_BIN="${CURSOR_BIN:-${CURSOR_TUNNEL_HOME}/cursor}"
if [[ "${CURSOR_BIN}" == ~* ]]; then
  CURSOR_BIN="${CURSOR_BIN/#\~/${HOME}}"
fi

mkdir -p "${CURSOR_TUNNEL_HOME}/logs"
exec > >(tee -a "${CURSOR_TUNNEL_HOME}/logs/tunnel-${SLURM_JOB_ID}.out") 2>&1

echo "Job ${SLURM_JOB_ID} on $(hostname) at $(date)"
echo "Tunnel dir: ${CURSOR_TUNNEL_HOME}"
echo "Tunnel name: ${TUNNEL_NAME}"

cd "${CURSOR_TUNNEL_HOME}"
export CURSOR_CLI_DISABLE_KEYCHAIN_ENCRYPT=1

exec "${CURSOR_BIN}" tunnel \
  --accept-server-license-terms \
  --name "${TUNNEL_NAME}"
