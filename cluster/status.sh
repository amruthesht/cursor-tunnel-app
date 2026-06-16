#!/usr/bin/env bash
# List running cursor tunnel Slurm jobs for the dashboard.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/config.env" ]]; then
  # shellcheck source=config.env
  source "${SCRIPT_DIR}/config.env"
fi

CURSOR_TUNNEL_HOME="${CURSOR_TUNNEL_HOME:-${SCRIPT_DIR}}"
prefix="${JOB_PREFIX:-cursor-tun-app}"
jobs_map="${CURSOR_TUNNEL_HOME}/jobs.map"
user="${USER:-${LOGNAME:-}}"

lookup_tunnel_name() {
  local jid="$1" jname="$2" tun=""
  if [[ -f "${jobs_map}" ]]; then
    tun="$(grep "^${jid}|" "${jobs_map}" 2>/dev/null | tail -1 | cut -d'|' -f2)"
  fi
  if [[ -z "${tun}" ]]; then
    tun="${jname#${prefix}-}"
    tun="${tun#cursor-tun-app-}"
    tun="${tun#cursor-tun-}"
    tun="${tun#ct-}"
    tun="${tun#sol-}"
    while [[ "${tun}" == *_ ]]; do tun="${tun%_}"; done
  fi
  printf '%s' "${tun}"
}

lookup_time_limit() {
  local jid="$1" lim=""
  if [[ -f "${jobs_map}" ]]; then
    lim="$(grep "^${jid}|" "${jobs_map}" 2>/dev/null | tail -1 | cut -d'|' -f3)"
  fi
  printf '%s' "${lim}"
}

looks_like_state() {
  local v="$1"
  [[ "${#v}" -le 3 && "${v}" =~ ^[A-Z]+$ ]]
}

is_tunnel_job() {
  local jid="$1" jname="$2"
  [[ "${jname}" == ct-* ]] && return 0
  [[ "${jname}" == "${prefix}-"* ]] && return 0
  [[ "${jname}" == cursor-tun-app-* ]] && return 0
  [[ "${jname}" == cursor-tun-* ]] && return 0
  [[ "${jname}" == sol-* ]] && return 0
  if [[ -f "${jobs_map}" ]] && grep -q "^${jid}|" "${jobs_map}" 2>/dev/null; then
    return 0
  fi
  return 1
}

enrich_from_scontrol() {
  local jid="$1" elapsed="$2" tlimit="$3"
  local line rt tl
  line="$(scontrol show job "${jid}" 2>/dev/null || true)"
  if [[ -n "${line}" ]]; then
    rt="$(printf '%s\n' "${line}" | sed -n 's/.* RunTime=\([^ ]*\).*/\1/p' | head -1)"
    tl="$(printf '%s\n' "${line}" | sed -n 's/.* TimeLimit=\([^ ]*\).*/\1/p' | head -1)"
    if [[ -n "${rt}" && "${rt}" != "00:00:00" ]]; then
      elapsed="${rt}"
    fi
    if [[ -n "${tl}" && "${tl}" != "NOT_SET" && "${tl}" != "NULL" ]] && ! looks_like_state "${tl}"; then
      tlimit="${tl}"
    fi
  fi
  if looks_like_state "${tlimit}" || [[ -z "${tlimit}" || "${tlimit}" == "NOT_SET" ]]; then
    tlimit="$(lookup_time_limit "${jid}")"
  fi
  printf '%s|%s' "${elapsed}" "${tlimit}"
}

echo "TUNNELS"
# Process substitution avoids pipefail + set -e failing when the while loop hits EOF.
while IFS='|' read -r jid elapsed tlimit state part jname; do
  [[ -z "${jid}" ]] && continue
  is_tunnel_job "${jid}" "${jname}" || continue
  if looks_like_state "${tlimit}"; then
    tlimit=""
  fi
  IFS='|' read -r elapsed tlimit < <(enrich_from_scontrol "${jid}" "${elapsed}" "${tlimit}") || true
  tun="$(lookup_tunnel_name "${jid}" "${jname}")"
  echo "${jid}|${elapsed}|${tlimit}|${state}|${part}||${tun}|${jname}"
done < <(squeue -u "${user}" -h -o "%i|%M|%l|%t|%P|%j" 2>/dev/null || true) || true

echo "---LOGS---"
ls -lt "${CURSOR_TUNNEL_HOME}/logs" 2>/dev/null | head -6 || true
