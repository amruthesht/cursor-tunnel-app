"""Parse and format Slurm time strings."""

from __future__ import annotations

import re

# Slurm job state codes (squeue %t) — not valid time limits.
SLURM_STATE_CODES = frozenset(
    {
        "R",
        "PD",
        "CG",
        "CD",
        "F",
        "NF",
        "SE",
        "ST",
        "S",
        "CA",
        "CF",
        "DR",
        "HS",
        "OM",
        "PR",
        "SI",
        "SO",
        "SP",
        "SS",
        "TO",
        "UN",
        "RS",
    }
)


def is_slurm_state_code(raw: str | None) -> bool:
    s = (raw or "").strip().upper()
    return bool(s) and s in SLURM_STATE_CODES


def normalize_time_limit(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s or is_slurm_state_code(s):
        return ""
    if s.upper() in {"NOT_SET", "N/A", "UNLIMITED", "INVALID", "+", "-", "NULL"}:
        return ""
    return s


def slurm_time_to_seconds(raw: str | None, *, kind: str = "elapsed") -> int | None:
    if not raw:
        return None
    s = raw.strip()
    if not s or s.upper() in {"NOT_SET", "N/A", "UNLIMITED", "INVALID", "+", "-"}:
        return None

    days = 0
    if "-" in s:
        day_part, s = s.split("-", 1)
        if day_part.isdigit():
            days = int(day_part)

    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        if s.isdigit():
            # Slurm often prints limits and short elapsed values as plain minutes.
            return int(s) * 60
        return None

    if len(nums) == 3:
        hours, minutes, seconds = nums
    elif len(nums) == 2:
        if kind == "limit":
            hours, minutes, seconds = nums[0], nums[1], 0
        else:
            hours, minutes, seconds = 0, nums[0], nums[1]
    elif len(nums) == 1:
        hours, minutes, seconds = 0, nums[0], 0
    else:
        return None

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def format_slurm_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def remaining_time(elapsed: str | None, time_limit: str | None) -> tuple[str, int | None]:
    limit_s = slurm_time_to_seconds(time_limit, kind="limit")
    elapsed_s = slurm_time_to_seconds(elapsed, kind="elapsed")
    if limit_s is None:
        return ("—", None)
    if elapsed_s is None:
        return (format_slurm_duration(limit_s), limit_s)
    rem = max(0, limit_s - elapsed_s)
    return (format_slurm_duration(rem), rem)


def clean_tunnel_name(name: str) -> str:
    n = (name or "").strip()
    if re.match(r"^.+_\d+$", n):
        return n
    return n.rstrip("_")
