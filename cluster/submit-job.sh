#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

GPUS=""
EXTRA_SBATCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cpus) CPUS="$2"; shift 2 ;;
    --mem) MEM="$2"; shift 2 ;;
    --time) TIME="$2"; shift 2 ;;
    --tunnel-name) TUNNEL_NAME="$2"; shift 2 ;;
    --partition) SLURM_PARTITION="$2"; shift 2 ;;
    --account) SLURM_ACCOUNT="$2"; shift 2 ;;
    --qos) SLURM_QOS="$2"; shift 2 ;;
    --gpus) GPUS="$2"; shift 2 ;;
    --extra-sbatch) EXTRA_SBATCH="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

: "${TUNNEL_NAME:?Pass --tunnel-name}"

JOB_NAME="$(slurm_job_name_for_tunnel "${TUNNEL_NAME}")"
job_script="${CURSOR_TUNNEL_HOME}/tunnel.slurm"
mapfile -t SLURM_EXTRA < <(slurm_extra_args)

GRES_ARGS=()
if [[ -n "${GPUS}" ]]; then
  gres="${GPUS}"
  [[ "${gres}" != gpu:* ]] && gres="gpu:${gres}"
  GRES_ARGS=(--gres="${gres}")
fi

EXTRA_ARGS=()
if [[ -n "${EXTRA_SBATCH}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS=(${EXTRA_SBATCH})
fi

# shellcheck disable=SC2068
job_id="$(sbatch --parsable \
  "${SLURM_EXTRA[@]}" \
  "${EXTRA_ARGS[@]}" \
  "${GRES_ARGS[@]}" \
  --nodes=1 \
  --ntasks=1 \
  --cpus-per-task="${CPUS}" \
  --mem="${MEM}" \
  --time="${TIME}" \
  --job-name="${JOB_NAME}" \
  --export=ALL,CURSOR_TUNNEL_HOME="${CURSOR_TUNNEL_HOME}",TUNNEL_NAME_OVERRIDE="${TUNNEL_NAME}" \
  "${job_script}")"

printf '%s|%s|%s\n' "${job_id}" "${TUNNEL_NAME}" "${TIME}" >> "${CURSOR_TUNNEL_HOME}/jobs.map"

echo "${job_id}|${TUNNEL_NAME}|${JOB_NAME}"
