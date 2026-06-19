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

# Slurm jobs usually have no systemd user session, so /run/user/$UID does not
# exist. Cursor git auth uses Unix sockets under XDG_RUNTIME_DIR — without this,
# terminal git push fails with ENOENT on vscode-git-*.sock.
# Prefer node-local SLURM temp; fall back to per-job /tmp (not shared home/NFS).
if [[ -n "${SLURM_TMPDIR:-}" && -d "${SLURM_TMPDIR}" ]]; then
  export XDG_RUNTIME_DIR="${SLURM_TMPDIR}/xdg-runtime"
else
  export XDG_RUNTIME_DIR="/tmp/cursor-xdg-${USER}-${SLURM_JOB_ID}"
fi
mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"

exec "${CURSOR_BIN}" tunnel \
  --accept-server-license-terms \
  --name "${TUNNEL_NAME}"
