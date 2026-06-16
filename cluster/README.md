# Cluster

Bash and Slurm files deployed to the HPC login node over SSH (into `~/cursor-tunnel/`).

The app uploads this folder on connect/deploy.

## Files

| File | Purpose |
|------|---------|
| `lib.sh` | Shared helpers, reads `config.env` |
| `config.env.example` | Template — copied to `config.env` on deploy |
| `submit-job.sh` | Parse CLI args, `sbatch`, append `jobs.map` |
| `status.sh` | List running tunnel jobs + recent log files |
| `stop-job.sh` | `scancel` one job |
| `stop-tunnel.sh` | Stop tunnel process inside allocation (if used) |
| `tunnel.slurm` | Slurm job script — runs `cursor tunnel` on compute node |

## Remote layout

```text
~/cursor-tunnel/
├── cursor              → Cursor CLI (you install this)
├── config.env
├── jobs.map            job_id|tunnel_name|time_limit
├── *.sh
├── tunnel.slurm
└── logs/
```

`jobs.map` maps Slurm IDs to tunnel names for the dashboard.

After edits here: dashboard → Advanced → Re-deploy scripts.

The Cursor CLI is installed automatically on connect if missing (default `~/cursor-tunnel/cursor`).
