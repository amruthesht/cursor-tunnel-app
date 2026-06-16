"""SSH client for cluster operations."""

from __future__ import annotations

import re
import shlex
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import paramiko

from branding import APP_SLUG, DEFAULT_REMOTE_DIR
from config_store import default_cursor_bin, default_remote_dir, load_config
from setup_status import clear_setup_status, set_setup_status
from slurm_time import clean_tunnel_name, is_slurm_state_code, normalize_time_limit, remaining_time
from tunnel_history import (
    dismiss_stopped,
    history_tunnel_name,
    mark_stopped,
    params_by_job_id,
    recent_launch_presets,
    record_launch,
    stopped_cards,
    sync_running,
)

SSH_MAX_RETRIES = 3
SSH_RETRY_DELAY_SEC = 0.75

@dataclass
class LoginSession:
    session_id: str
    code: str
    url: str
    provider: str
    status: str = "pending"
    _client: paramiko.SSHClient | None = None
    _channel: paramiko.Channel | None = None


login_sessions: dict[str, LoginSession] = {}
login_lock = threading.Lock()
_remote_base_cache: dict[str, str] = {}
_ssh_pool: dict[str, paramiko.SSHClient] = {}
_pool_locks: dict[str, threading.Lock] = {}
_pool_guard = threading.Lock()


def remote_dir(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    user = (cfg.get("ssh_user") or "").strip()
    rd = (cfg.get("remote_dir") or "").strip()
    if rd.startswith("$HOME/"):
        rd = "~/" + rd[len("$HOME/") :]
    elif rd == "$HOME":
        rd = "~"
    # Default remote scripts dir on login node
    if not rd:
        return default_remote_dir(user)
    norm = rd.rstrip("/")
    if norm in {DEFAULT_REMOTE_DIR, "$HOME/cursor-tunnel"}:
        return default_remote_dir(user)
    if user and norm in {
        f"{DEFAULT_REMOTE_DIR}/{user}",
        f"~/cursor-tunnel/{user}",
        f"$HOME/cursor-tunnel/{user}",
    }:
        return default_remote_dir(user)
    return rd


def _cache_key(cfg: dict) -> str:
    return f"{cfg.get('ssh_user')}@{cfg.get('ssh_host')}:{cfg.get('ssh_port', 22)}:{remote_dir(cfg)}"


def _host_lock(cfg: dict) -> threading.Lock:
    key = _cache_key(cfg)
    with _pool_guard:
        if key not in _pool_locks:
            _pool_locks[key] = threading.Lock()
        return _pool_locks[key]


def clear_ssh_pool(cfg: dict | None = None) -> None:
    """Drop pooled SSH connections (e.g. on disconnect or after errors)."""
    with _pool_guard:
        keys = [_cache_key(cfg)] if cfg else list(_ssh_pool.keys())
    for key in keys:
        with _pool_guard:
            client = _ssh_pool.pop(key, None)
        if client:
            try:
                client.close()
            except Exception:
                pass


def _drop_pooled_client(cfg: dict) -> None:
    key = _cache_key(cfg)
    with _pool_guard:
        client = _ssh_pool.pop(key, None)
    if client:
        try:
            client.close()
        except Exception:
            pass


def _borrow_client(cfg: dict, *, fresh: bool = False) -> paramiko.SSHClient:
    key = _cache_key(cfg)
    if not fresh:
        with _pool_guard:
            existing = _ssh_pool.get(key)
        if existing:
            try:
                transport = existing.get_transport()
                if transport and transport.is_active():
                    return existing
            except Exception:
                pass
            _drop_pooled_client(cfg)
    client = connect(cfg)
    with _pool_guard:
        _ssh_pool[key] = client
    return client


def remote_base(cfg: dict | None = None, *, refresh: bool = False) -> str:
    """Absolute remote scripts path on the cluster (cached)."""
    cfg = cfg or load_config()
    key = _cache_key(cfg)
    if not refresh and key in _remote_base_cache:
        return _remote_base_cache[key]

    home_out, _, code = run_remote("echo $HOME", cfg, timeout=20)
    home = home_out.strip().splitlines()[-1].strip() if home_out.strip() else ""
    if code != 0 or not home.startswith("/"):
        home_out, _, code = run_remote("cd ~ && pwd", cfg, timeout=20)
        home = home_out.strip().splitlines()[-1].strip() if home_out.strip() else ""
    if not home.startswith("/"):
        raise RuntimeError("Could not resolve home directory on cluster")

    rd = remote_dir(cfg)
    if rd.startswith("~/"):
        base = f"{home}/{rd[2:].lstrip('/')}"
    elif rd.startswith("/"):
        base = rd
    else:
        base = f"{home}/{rd.lstrip('/')}"

    _remote_base_cache[key] = base
    return base


def resolve_remote_dir(cfg: dict | None = None) -> str:
    return remote_base(cfg)


def ensure_remote_dir(cfg: dict | None = None) -> None:
    base = remote_base(cfg)
    run_remote(f"mkdir -p {base}/logs", cfg, timeout=30)


def shell_cd(cfg: dict | None = None) -> str:
    base = remote_base(cfg)
    if not base.startswith("/"):
        raise RuntimeError(f"Invalid remote path: {base}")
    return f"cd {base}"


def shell_path(cfg: dict | None = None, *parts: str) -> str:
    base = remote_base(cfg).rstrip("/")
    return "/".join([base, *parts]) if parts else base


def connect(cfg: dict | None = None) -> paramiko.SSHClient:
    cfg = cfg or load_config()
    if not cfg.get("ssh_host") or not cfg.get("ssh_user"):
        raise ValueError("Set SSH host and username in Settings")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    kwargs: dict = {
        "hostname": cfg["ssh_host"],
        "username": cfg["ssh_user"],
        "port": int(cfg.get("ssh_port") or 22),
        "timeout": 30,
        "allow_agent": True,
        "look_for_keys": True,
    }

    key_path = (cfg.get("ssh_key_path") or "").strip()
    if key_path:
        expanded = str(Path(key_path).expanduser())
        if Path(expanded).exists():
            kwargs["key_filename"] = expanded

    password = cfg.get("ssh_password") or ""
    if password:
        kwargs["password"] = password

    client.connect(**kwargs, banner_timeout=60, auth_timeout=60)
    transport = client.get_transport()
    if transport:
        transport.set_keepalive(30)
    return client


def run_remote(command: str, cfg: dict | None = None, timeout: int = 120) -> tuple[str, str, int]:
    cfg = cfg or load_config()
    lock = _host_lock(cfg)
    last_exc: Exception | None = None
    for attempt in range(SSH_MAX_RETRIES):
        with lock:
            try:
                client = _borrow_client(cfg, fresh=(attempt > 0))
                _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                out = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                code = stdout.channel.recv_exit_status()
                if code != 0:
                    print(f"[{APP_SLUG}] remote failed ({code}): {command!r}")
                    if err.strip():
                        print(f"[{APP_SLUG}] stderr: {err.strip()[:500]}")
                return out, err, code
            except (paramiko.SSHException, OSError, EOFError) as exc:
                last_exc = exc
                _drop_pooled_client(cfg)
        if attempt < SSH_MAX_RETRIES - 1:
            time.sleep(SSH_RETRY_DELAY_SEC * (attempt + 1))
    raise paramiko.SSHException(str(last_exc) if last_exc else "SSH connection failed")


def effective_cursor_bin(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    custom = (cfg.get("defaults", {}).get("cursor_bin") or "").strip()
    if custom:
        return custom
    return default_cursor_bin()


def _cursor_target_shell_var(cfg: dict | None = None) -> str:
    """Bash snippet that sets TARGET to the expanded cursor CLI path."""
    raw = effective_cursor_bin(cfg)
    quoted = shlex.quote(raw)
    return f'TARGET="$(eval echo {quoted})"'


def cursor_cli_ready(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    cmd = (
        f"{_cursor_target_shell_var(cfg)}; "
        f'[ -x "$TARGET" ] && "$TARGET" --version >/dev/null 2>&1 && echo OK'
    )
    try:
        out, _, code = run_remote(cmd, cfg, timeout=30)
        return code == 0 and "OK" in out
    except Exception:
        return False


def ensure_cursor_cli(cfg: dict | None = None) -> dict:
    """Install Cursor CLI on the cluster when missing at the configured path."""
    cfg = cfg or load_config()
    target = effective_cursor_bin(cfg)

    set_setup_status("check", f"Checking Cursor CLI at {target}…")
    if cursor_cli_ready(cfg):
        return {"ok": True, "skipped": True, "message": f"Cursor CLI ready at {target}"}

    set_setup_status("download", f"Downloading Cursor CLI for {target}…")
    install_cmd = f"""
set -euo pipefail
{_cursor_target_shell_var(cfg)}
if [ -x "$TARGET" ] && "$TARGET" --version >/dev/null 2>&1; then
  echo OK
  exit 0
fi
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) TAG=cli-alpine-x64 ;;
  aarch64|arm64) TAG=cli-alpine-arm64 ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 2
    ;;
esac
TMP="$(mktemp -d)"
cleanup() {{ rm -rf "$TMP"; }}
trap cleanup EXIT
cd "$TMP"
if ! curl -fSL "https://api2.cursor.sh/updates/download-latest?os=${{TAG}}" -o cursor_cli.tar.gz; then
  echo "Cursor CLI download failed (check cluster internet access)" >&2
  exit 3
fi
tar -xzf cursor_cli.tar.gz
if [ ! -f cursor ]; then
  echo "cursor binary missing in downloaded package" >&2
  ls -la >&2 || true
  exit 4
fi
mkdir -p "$(dirname "$TARGET")"
mv -f cursor "$TARGET"
chmod +x "$TARGET"
"$TARGET" --version
echo INSTALLED
""".strip()
    try:
        out, err, code = run_remote(install_cmd, cfg, timeout=300)
    except Exception as exc:
        return {"ok": False, "error": f"Cursor CLI install failed: {exc}"}

    if code != 0:
        detail = (err or out).strip().splitlines()
        msg = detail[-1] if detail else f"install exited {code}"
        return {"ok": False, "error": f"Cursor CLI install failed: {msg}"}

    set_setup_status("verify", "Verifying Cursor CLI…")
    if not cursor_cli_ready(cfg):
        return {"ok": False, "error": "Cursor CLI install finished but the binary is not executable"}

    base = remote_base(cfg)
    default_link = f"{base}/cursor"
    link_cmd = (
        f"{_cursor_target_shell_var(cfg)}; "
        f'if [ "$TARGET" != "{default_link}" ] && [ -d "{base}" ]; then '
        f'ln -sf "$TARGET" "{default_link}"; fi'
    )
    try:
        run_remote(link_cmd, cfg, timeout=30)
    except Exception:
        pass

    version_line = next((ln.strip() for ln in out.splitlines() if ln.strip() and ln.strip() != "INSTALLED"), "")
    message = f"Installed Cursor CLI to {target}"
    if version_line:
        message = f"{message} ({version_line})"
    set_setup_status("done", message)
    return {"ok": True, "installed": True, "message": message}


def _apply_cursor_cli_result(result: dict, cursor: dict) -> dict:
    if not cursor.get("ok"):
        result["ok"] = False
        result["error"] = cursor.get("error", "Cursor CLI setup failed")
        return result
    if cursor.get("installed"):
        result["cursor_cli"] = cursor.get("message", "Cursor CLI installed")
    elif cursor.get("skipped"):
        result["cursor_cli"] = cursor.get("message", "Cursor CLI ready")
    return result


def _sed_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace('"', '\\"')


def sync_remote_config_env(cfg: dict | None = None) -> None:
    """Write CURSOR_TUNNEL_HOME and CURSOR_BIN to remote config.env."""
    cfg = cfg or load_config()
    base = remote_base(cfg)
    cursor_bin = effective_cursor_bin(cfg)
    run_remote(
        f"{shell_cd(cfg)} && "
        f"[ -f config.env ] || cp config.env.example config.env; "
        f"sed -i 's|^CURSOR_TUNNEL_HOME=.*|CURSOR_TUNNEL_HOME=\"{_sed_escape(base)}\"|' config.env; "
        f"sed -i 's|^CURSOR_BIN=.*|CURSOR_BIN=\"{_sed_escape(cursor_bin)}\"|' config.env",
        cfg,
        timeout=30,
    )


def cursor_bin(cfg: dict | None = None) -> str:
    return effective_cursor_bin(cfg)


def parse_device_login(text: str, provider: str) -> tuple[str | None, str | None]:
    code_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", text, re.I)
    code = code_match.group(1).upper() if code_match else None
    url_match = re.search(r"https?://[^\s\]]+", text)
    url = url_match.group(0).rstrip(".,)") if url_match else None
    if not url:
        url = (
            "https://github.com/login/device"
            if provider == "github"
            else "https://microsoft.com/devicelogin"
        )
    return code, url


def test_connection(cfg: dict | None = None) -> dict:
    try:
        out, err, code = run_remote("echo OK && hostname", cfg, timeout=20)
        if code != 0:
            return {"ok": False, "error": (err or out).strip() or f"exit {code}"}
        return {"ok": True, "message": f"Connected to {out.strip()}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def cluster_scripts_present(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    submit = shell_path(cfg, "submit-job.sh")
    slurm = shell_path(cfg, "tunnel.slurm")
    cmd = f"test -f {submit} && test -f {slurm} && echo YES"
    try:
        out, _, code = run_remote(cmd, cfg, timeout=20)
        return code == 0 and "YES" in out
    except Exception:
        return False


def deploy_cluster_scripts(bundle_dir: Path, cfg: dict | None = None, *, force: bool = False) -> dict:
    cfg = cfg or load_config()
    if not force and cluster_scripts_present(cfg):
        rd = remote_dir(cfg)
        return {
            "ok": True,
            "skipped": True,
            "message": f"Cluster scripts already present at {rd} (skipped)",
        }

    rd = remote_dir(cfg)
    files = [
        "lib.sh",
        "submit-job.sh",
        "status.sh",
        "stop-job.sh",
        "stop-tunnel.sh",
        "tunnel.slurm",
        "config.env.example",
    ]

    try:
        ensure_remote_dir(cfg)
        remote_base_path = remote_base(cfg)

        lock = _host_lock(cfg)
        with lock:
            client = _borrow_client(cfg)
            sftp = client.open_sftp()
            try:
                for name in files:
                    local = bundle_dir / name
                    if not local.exists():
                        continue
                    sftp.put(str(local), f"{remote_base_path}/{name}")
            finally:
                sftp.close()

        run_remote(
            f"{shell_cd(cfg)} && chmod +x *.sh 2>/dev/null; "
            f"[ -f config.env ] || cp config.env.example config.env",
            cfg,
            timeout=30,
        )
        sync_remote_config_env(cfg)
        return {"ok": True, "skipped": False, "message": f"Deployed scripts to {remote_base_path}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def ensure_cluster_scripts(bundle_dir: Path, cfg: dict | None = None) -> dict:
    """Deploy cluster scripts only if not already on the login node."""
    return deploy_cluster_scripts(bundle_dir, cfg, force=False)


def test_connection_and_setup(
    bundle_dir: Path, cfg: dict | None = None, *, force_deploy: bool = False
) -> dict:
    clear_setup_status()
    try:
        result = test_connection(cfg)
        if not result.get("ok"):
            return result
        try:
            ensure_remote_dir(cfg)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if force_deploy:
            deploy = deploy_cluster_scripts(bundle_dir, cfg, force=True)
        else:
            deploy = ensure_cluster_scripts(bundle_dir, cfg)
        if deploy.get("skipped"):
            result["scripts"] = deploy["message"]
        elif deploy.get("ok"):
            result["scripts"] = deploy["message"]
        else:
            result["scripts_error"] = deploy.get("error", "Script deploy failed")

        cursor = ensure_cursor_cli(cfg)
        return _apply_cursor_cli_result(result, cursor)
    finally:
        clear_setup_status()


def submit_job(params: dict, cfg: dict | None = None, bundle_dir: Path | None = None) -> dict:
    cfg = cfg or load_config()
    if params.get("cursor_bin") is not None:
        cfg = {
            **cfg,
            "defaults": {**cfg.get("defaults", {}), "cursor_bin": params.get("cursor_bin") or ""},
        }
    if bundle_dir is not None:
        deploy = ensure_cluster_scripts(bundle_dir, cfg)
        if not deploy.get("ok"):
            return {"ok": False, "error": deploy.get("error", "Could not deploy cluster scripts")}

    clear_setup_status()
    try:
        cursor = ensure_cursor_cli(cfg)
        if not cursor.get("ok"):
            return {"ok": False, "error": cursor.get("error", "Cursor CLI setup failed")}
    finally:
        clear_setup_status()

    try:
        sync_remote_config_env(cfg)
    except Exception as exc:
        return {"ok": False, "error": f"Could not update remote config: {exc}"}

    mem = params.get("mem") or params.get("mem_gib") or cfg["defaults"].get("mem_gib") or cfg["defaults"].get("mem", "8")
    mem_str = str(mem).strip()
    if mem_str.isdigit():
        mem_str = f"{mem_str}G"

    args = [f"{shell_cd(cfg)} && ./submit-job.sh"]
    submit_fields = [
        ("cpus", "--cpus"),
        ("time", "--time"),
        ("tunnel_name", "--tunnel-name"),
        ("partition", "--partition"),
        ("account", "--account"),
        ("qos", "--qos"),
        ("gpus", "--gpus"),
        ("extra_sbatch", "--extra-sbatch"),
    ]
    merged = {
        **cfg.get("defaults", {}),
        **params,
        "mem": mem_str,
        "cursor_bin": params.get("cursor_bin", cfg.get("defaults", {}).get("cursor_bin", "")),
    }
    for key, flag in submit_fields:
        val = merged.get(key)
        if val not in (None, ""):
            args.append(f"{flag} {shlex.quote(str(val))}")
    args.append(f"--mem {shlex.quote(mem_str)}")

    cmd = " ".join(args)
    try:
        out, err, code = run_remote(cmd, cfg, timeout=90)
        if code != 0:
            return {"ok": False, "error": f"{(err or out).strip()} (remote: {remote_base(cfg)})"}
        job_id = out.strip().splitlines()[-1]
        tunnel_name = params.get("tunnel_name") or cfg["defaults"]["tunnel_name"]
        if "|" in job_id:
            parts = job_id.split("|")
            job_id = parts[0]
            if len(parts) > 1:
                tunnel_name = parts[1]
        record_launch(
            job_id,
            tunnel_name,
            {
                "tunnel_name": tunnel_name,
                "cpus": merged.get("cpus"),
                "mem_gib": str(merged.get("mem_gib") or mem_str).rstrip("Gg"),
                "mem": mem_str,
                "time": merged.get("time"),
                "partition": merged.get("partition"),
                "account": merged.get("account"),
                "qos": merged.get("qos"),
                "gpus": merged.get("gpus") or "",
                "extra_sbatch": merged.get("extra_sbatch") or "",
                "cursor_bin": merged.get("cursor_bin") or effective_cursor_bin(cfg),
            },
        )
        return {
            "ok": True,
            "job_id": job_id,
            "tunnel_name": tunnel_name,
            "message": "Tunnel started. It keeps running after you close this app.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _apply_job_time_fields(job: dict) -> None:
    elapsed = (job.get("elapsed") or "").strip()
    time_limit = normalize_time_limit(job.get("time_limit"))
    if not time_limit:
        params = job.get("params") or {}
        time_limit = normalize_time_limit(params.get("time"))
    job["time_limit"] = time_limit
    rem_display, rem_seconds = remaining_time(elapsed, time_limit)
    job["remaining"] = rem_display
    job["remaining_seconds"] = rem_seconds
    state = (job.get("state") or "").strip()
    if is_slurm_state_code(state):
        job["state_label"] = {
            "R": "Running",
            "PD": "Pending",
            "CG": "Completing",
            "CD": "Completed",
            "F": "Failed",
            "TO": "Timeout",
        }.get(state, state)
    else:
        job["state_label"] = state or "—"


def _parse_status_output(out: str) -> tuple[list[dict], list[dict]]:
    jobs: list[dict] = []
    logs: list[dict] = []
    section = None
    for line in out.splitlines():
        line = line.strip()
        if line == "TUNNELS":
            section = "tunnels"
            continue
        if line == "---LOGS---":
            section = "logs"
            continue
        if section == "tunnels" and line and "|" in line:
            parts = line.split("|")
            if len(parts) >= 7:
                elapsed = parts[1]
                time_limit = parts[2]
                tunnel_name = clean_tunnel_name(parts[6])
                job = {
                    "job_id": parts[0],
                    "elapsed": elapsed,
                    "time_limit": time_limit,
                    "state": parts[3],
                    "partition": parts[4],
                    "qos": parts[5],
                    "tunnel_name": tunnel_name,
                    "job_name": parts[7] if len(parts) >= 8 else "",
                }
                _apply_job_time_fields(job)
                jobs.append(job)
        elif section == "logs" and line and not line.startswith("total"):
            name = line.split()[-1] if line.split() else line
            if name.endswith(".out"):
                logs.append({"name": name})
    return jobs, logs


def job_status(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    try:
        out, err, code = run_remote(f"{shell_cd(cfg)} && ./status.sh", cfg, timeout=45)
        jobs, logs = _parse_status_output(out)
        if jobs or "TUNNELS" in out:
            jobs = _merge_job_status(jobs)
            return {
                "ok": True,
                "jobs": jobs,
                "recent_logs": logs[:5],
            }
        if code != 0:
            msg = (err or out).strip()
            if msg in ("TUNNELS", "---LOGS---") or msg.startswith("TUNNELS\n"):
                msg = "Could not read tunnel status from cluster (try Re-deploy scripts on Connect)"
            return {"ok": False, "error": msg or f"status.sh failed (exit {code})"}
        jobs = _merge_job_status(jobs)
        return {"ok": True, "jobs": jobs, "recent_logs": logs[:5]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _merge_job_status(jobs: list[dict]) -> list[dict]:
    active_ids = {str(j["job_id"]) for j in jobs}
    sync_running(active_ids)
    saved = params_by_job_id()
    for job in jobs:
        job["is_history"] = False
        jid = str(job.get("job_id", ""))
        if jid in saved:
            job["params"] = saved[jid]
        _apply_job_time_fields(job)
    history = stopped_cards()
    history = [h for h in history if str(h.get("job_id")) not in active_ids]
    return jobs + history


def dismiss_stopped_job(job_id: str) -> dict:
    if dismiss_stopped(job_id):
        return {"ok": True, "message": "Removed from recent stopped"}
    return {"ok": False, "error": "Stopped tunnel not found in history"}


def stop_job(job_id: str, cfg: dict | None = None, meta: dict | None = None) -> dict:
    cfg = cfg or load_config()
    if not job_id or not str(job_id).isdigit():
        return {"ok": False, "error": "Invalid job ID"}
    meta = meta or {}
    tunnel_name = (meta.get("tunnel_name") or "").strip()
    params = meta.get("params") if isinstance(meta.get("params"), dict) else None
    saved = params_by_job_id()
    jid = str(job_id)
    if not params and jid in saved:
        params = saved[jid]
    if not tunnel_name:
        tunnel_name = (params or {}).get("tunnel_name") or history_tunnel_name(jid)
    try:
        out, err, code = run_remote(
            f"{shell_cd(cfg)} && ./stop-job.sh {shlex.quote(str(job_id))}",
            cfg,
            timeout=45,
        )
        if code != 0:
            return {"ok": False, "error": (err or out).strip()}
        mark_stopped(job_id, tunnel_name=tunnel_name, params=params)
        return {"ok": True, "job_id": job_id, "message": f"Stopped tunnel job {job_id}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def stop_jobs(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    try:
        out, err, code = run_remote(f"{shell_cd(cfg)} && ./stop-tunnel.sh", cfg, timeout=45)
        if code != 0 and "NONE" not in out:
            return {"ok": False, "error": (err or out).strip()}
        cancelled = out.strip().split() if out.strip() != "NONE" else []
        return {
            "ok": True,
            "cancelled": cancelled,
            "message": "No running jobs" if not cancelled else f"Stopped {len(cancelled)} job(s)",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _wait_login(session_id: str) -> None:
    with login_lock:
        session = login_sessions.get(session_id)
    if not session or not session._channel:
        return
    ch = session._channel
    try:
        while not ch.exit_status_ready():
            time.sleep(0.5)
        status = ch.recv_exit_status()
        session.status = "complete" if status == 0 else "failed"
    except Exception:
        session.status = "failed"
    finally:
        if session._client:
            session._client.close()


def start_login(provider: str, cfg: dict | None = None, bundle_dir: Path | None = None) -> dict:
    import uuid

    cfg = cfg or load_config()
    if bundle_dir is not None:
        deploy = ensure_cluster_scripts(bundle_dir, cfg)
        if not deploy.get("ok"):
            return {"ok": False, "error": deploy.get("error", "Could not deploy cluster scripts")}

    clear_setup_status()
    try:
        cursor = ensure_cursor_cli(cfg)
        if not cursor.get("ok"):
            return {"ok": False, "error": cursor.get("error", "Cursor CLI setup failed")}
    finally:
        clear_setup_status()

    cb = cursor_bin(cfg)
    cmd = (
        f"{shell_cd(cfg)} && "
        f"export CURSOR_CLI_DISABLE_KEYCHAIN_ENCRYPT=1 && "
        f"{cb} tunnel user login --provider {shlex.quote(provider)}"
    )

    try:
        client = connect(cfg)
        channel = client.get_transport().open_session()  # type: ignore[union-attr]
        channel.get_pty()
        channel.exec_command(cmd)

        collected = ""
        code = None
        url = None
        deadline = time.time() + 60
        while time.time() < deadline:
            if channel.recv_ready():
                collected += channel.recv(4096).decode("utf-8", errors="replace")
                code, url = parse_device_login(collected, provider)
                if code:
                    break
            if channel.exit_status_ready():
                break
            time.sleep(0.2)

        if not code:
            channel.close()
            client.close()
            return {
                "ok": False,
                "error": "Could not read device code from cluster.",
                "log": collected[-1500:],
            }

        session_id = str(uuid.uuid4())
        session = LoginSession(
            session_id=session_id,
            code=code,
            url=url or "https://github.com/login/device",
            provider=provider,
            _client=client,
            _channel=channel,
        )
        with login_lock:
            login_sessions[session_id] = session
        threading.Thread(target=_wait_login, args=(session_id,), daemon=True).start()

        return {
            "ok": True,
            "session_id": session_id,
            "code": code,
            "url": session.url,
            "provider": provider,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def login_status(session_id: str) -> dict:
    with login_lock:
        session = login_sessions.get(session_id)
    if not session:
        return {"ok": False, "error": "Session not found"}
    return {
        "ok": True,
        "status": session.status,
        "code": session.code,
        "url": session.url,
    }
