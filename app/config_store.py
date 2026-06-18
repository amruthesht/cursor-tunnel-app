"""Local app configuration (SSH + defaults)."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from branding import APP_SLUG, BUILTIN_SSH_HOSTS, DEFAULT_CURSOR_BIN, DEFAULT_REMOTE_DIR

DEFAULT_CONFIG = {
    "ssh_host": BUILTIN_SSH_HOSTS[0],
    "ssh_hosts": list(BUILTIN_SSH_HOSTS),
    "ssh_user": "",
    "ssh_port": 22,
    "ssh_key_path": "",
    "ssh_password": "",
    "remote_dir": "",
    "listen_host": "127.0.0.1",
    "listen_port": 8765,
    "open_browser": True,
    "shutdown_when_idle": True,
    "idle_seconds": 20,
    "redeploy_on_connect": False,
    "defaults": {
        "cpus": "4",
        "mem": "8",
        "mem_gib": "8",
        "time": "04:00:00",
        "tunnel_name": "",
        "gpus": "",
        "extra_sbatch": "",
        "partition": "public",
        "account": "",
        "qos": "public",
        "auth_provider": "github",
        "cursor_bin": "",
    },
}


def default_tunnel_name(ssh_user: str | None = None) -> str:
    user = (ssh_user or "").strip() or "user"
    return f"ct_{user}"


def default_remote_dir(ssh_user: str | None = None) -> str:
    return DEFAULT_REMOTE_DIR


def default_cursor_bin() -> str:
    return DEFAULT_CURSOR_BIN


def ssh_hosts_for(cfg: dict) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for host in [*BUILTIN_SSH_HOSTS, *(cfg.get("ssh_hosts") or [])]:
        h = str(host).strip()
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    current = (cfg.get("ssh_host") or "").strip()
    if current and current not in seen:
        out.append(current)
    return out


def app_config_dir() -> Path:
    from platform_detect import is_android

    if is_android():
        from org.beeware.android import MainActivity

        activity = MainActivity.singletonThis
        base = Path(activity.getFilesDir().getAbsolutePath()) / APP_SLUG
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_SLUG
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_SLUG
    else:
        base = Path.home() / ".config" / APP_SLUG
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return app_config_dir() / "config.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        from platform_detect import is_android

        if is_android():
            cfg["open_browser"] = False
            cfg["shutdown_when_idle"] = False
        else:
            key = Path.home() / ".ssh" / "id_rsa"
            if key.exists():
                cfg["ssh_key_path"] = str(key)
        from ssh_keys import private_key_path

        app_key = private_key_path()
        if app_key.is_file():
            cfg["ssh_key_path"] = str(app_key)
        return cfg
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    merged = deepcopy(DEFAULT_CONFIG)
    merged.update({k: v for k, v in data.items() if k != "defaults"})
    merged["defaults"] = {**DEFAULT_CONFIG["defaults"], **data.get("defaults", {})}
    merged["ssh_hosts"] = ssh_hosts_for(merged)
    for key in ("ssh_host", "ssh_user", "ssh_port", "remote_dir"):
        if not merged.get(key) and DEFAULT_CONFIG.get(key):
            merged[key] = DEFAULT_CONFIG[key]
    for key in ("partition", "qos"):
        if not merged["defaults"].get(key) and DEFAULT_CONFIG["defaults"].get(key):
            merged["defaults"][key] = DEFAULT_CONFIG["defaults"][key]
    from platform_detect import is_android

    if is_android():
        merged["open_browser"] = False
        merged["shutdown_when_idle"] = False
    if not merged.get("ssh_key_path"):
        from ssh_keys import private_key_path

        app_key = private_key_path()
        if app_key.is_file():
            merged["ssh_key_path"] = str(app_key)
    return merged


def dashboard_urls(cfg: dict | None = None) -> list[str]:
    """URLs where the local dashboard is reachable."""
    cfg = cfg or load_config()
    port = int(cfg.get("listen_port") or 8765)
    host = (cfg.get("listen_host") or "127.0.0.1").strip()
    urls: list[str] = []

    def add(h: str) -> None:
        url = f"http://{h}:{port}"
        if url not in urls:
            urls.append(url)

    if host in ("0.0.0.0", "::", ""):
        add("127.0.0.1")
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                add(sock.getsockname()[0])
        except OSError:
            pass
    else:
        add("127.0.0.1" if host in ("localhost",) else host)
    return urls


def save_config(cfg: dict) -> None:
    path = config_path()
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
