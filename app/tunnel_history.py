"""Local tunnel launch history for stopped cards and resubmit."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

from config_store import app_config_dir

HISTORY_FILE = app_config_dir() / "tunnel-history.json"
MAX_STOPPED = 8
STOPPED_TTL_SEC = 24 * 3600


def _load() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _prune(entries: list[dict]) -> list[dict]:
    now = time.time()
    kept: list[dict] = []
    stopped_count = 0
    for entry in reversed(entries):
        status = entry.get("status", "stopped")
        if status == "stopped":
            stopped_at = float(entry.get("stopped_at") or entry.get("updated_at") or 0)
            if now - stopped_at > STOPPED_TTL_SEC:
                continue
            if stopped_count >= MAX_STOPPED:
                continue
            stopped_count += 1
        kept.append(entry)
    kept.reverse()
    return kept


def record_launch(job_id: str, tunnel_name: str, params: dict) -> None:
    entries = _prune(_load())
    params = deepcopy(params)
    params["tunnel_name"] = tunnel_name
    now = time.time()
    entries.append(
        {
            "job_id": str(job_id),
            "tunnel_name": tunnel_name,
            "status": "running",
            "submitted_at": now,
            "updated_at": now,
            "params": params,
        }
    )
    _save(_prune(entries))


def mark_stopped(job_id: str, tunnel_name: str = "", params: dict | None = None) -> None:
    entries = _load()
    jid = str(job_id)
    now = time.time()
    found = False
    for entry in entries:
        if str(entry.get("job_id")) == jid:
            entry["status"] = "stopped"
            entry["stopped_at"] = now
            entry["updated_at"] = now
            if tunnel_name:
                entry["tunnel_name"] = tunnel_name
            if params:
                entry["params"] = deepcopy(params)
            found = True
            break
    if not found:
        p = deepcopy(params or {})
        if tunnel_name:
            p.setdefault("tunnel_name", tunnel_name)
        entries.append(
            {
                "job_id": jid,
                "tunnel_name": tunnel_name or p.get("tunnel_name") or f"job_{jid}",
                "status": "stopped",
                "stopped_at": now,
                "updated_at": now,
                "submitted_at": now,
                "params": p,
            }
        )
    _save(_prune(entries))


def history_tunnel_name(job_id: str) -> str:
    jid = str(job_id)
    for entry in _load():
        if str(entry.get("job_id")) == jid:
            return str(entry.get("tunnel_name") or "")
    return ""


def dismiss_stopped(job_id: str) -> bool:
    """Remove a stopped tunnel card from local history."""
    entries = _load()
    jid = str(job_id)
    kept = [e for e in entries if str(e.get("job_id")) != jid]
    if len(kept) == len(entries):
        return False
    _save(_prune(kept))
    return True


def sync_running(active_job_ids: set[str]) -> None:
    """Mark history entries as stopped when they disappear from squeue."""
    entries = _load()
    now = time.time()
    changed = False
    for entry in entries:
        if entry.get("status") != "running":
            continue
        jid = str(entry.get("job_id", ""))
        if jid and jid not in active_job_ids:
            entry["status"] = "stopped"
            entry["stopped_at"] = now
            entry["updated_at"] = now
            changed = True
    if changed:
        _save(_prune(entries))


def stopped_cards() -> list[dict]:
    entries = _prune(_load())
    out = []
    for entry in reversed(entries):
        if entry.get("status") != "stopped":
            continue
        params = entry.get("params") or {}
        out.append(
            {
                "job_id": entry.get("job_id", ""),
                "tunnel_name": entry.get("tunnel_name", ""),
                "state": "stopped",
                "is_history": True,
                "stopped_at": entry.get("stopped_at"),
                "params": params,
                "elapsed": "",
                "time_limit": params.get("time", ""),
                "remaining": "",
                "partition": params.get("partition", ""),
                "qos": params.get("qos", ""),
            }
        )
    return out


def params_by_job_id() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for entry in _load():
        jid = str(entry.get("job_id", ""))
        params = entry.get("params")
        if jid and isinstance(params, dict) and params:
            out[jid] = deepcopy(params)
    return out


def _preset_key(params: dict) -> str:
    keys = ("cpus", "mem_gib", "mem", "time", "account", "qos", "gpus", "cursor_bin", "extra_sbatch", "partition")
    blob = {k: str(params.get(k) or "") for k in keys}
    return json.dumps(blob, sort_keys=True)


def recent_launch_presets(max_presets: int = 8) -> list[dict]:
    """Distinct recent launch parameter sets (newest first)."""
    seen: set[str] = set()
    out: list[dict] = []
    for entry in reversed(_prune(_load())):
        params = entry.get("params") or {}
        if not params.get("cpus") and not params.get("time"):
            continue
        key = _preset_key(params)
        if key in seen:
            continue
        seen.add(key)
        parts = [
            f"{params.get('cpus', '?')} CPU" if params.get("cpus") else "",
            f"{params.get('mem_gib') or params.get('mem', '')} mem".strip(),
            params.get("time", ""),
            params.get("account", ""),
        ]
        label = " · ".join(p for p in parts if p) or entry.get("tunnel_name", "Previous setup")
        out.append({"id": str(len(out)), "label": label, "params": deepcopy(params)})
        if len(out) >= max_presets:
            break
    return out
