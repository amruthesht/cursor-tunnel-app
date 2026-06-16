#!/usr/bin/env bash
# Stop one tunnel job by Slurm job ID.
set -euo pipefail

job_id="${1:-}"
if [[ -z "${job_id}" ]]; then
  echo "usage: stop-job.sh JOBID" >&2
  exit 1
fi

scancel "${job_id}"
echo "stopped|${job_id}"
