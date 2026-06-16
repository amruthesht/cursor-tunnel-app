#!/usr/bin/env python3
"""Local dashboard API — SSH into cluster via VPN, no cluster-side server."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from branding import APP_DISPLAY_NAME, APP_SLUG
from version import __version__
from config_store import (
    dashboard_urls,
    default_cursor_bin,
    default_tunnel_name,
    load_config,
    save_config,
    ssh_hosts_for,
)
from setup_status import get_setup_status
from ssh_client import (
    clear_ssh_pool,
    deploy_cluster_scripts,
    dismiss_stopped_job,
    job_status,
    login_status,
    remote_dir as cluster_remote_dir,
    start_login,
    stop_job,
    stop_jobs,
    submit_job,
    test_connection_and_setup,
)
from tunnel_history import recent_launch_presets

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    APP_ROOT = Path(__file__).resolve().parent

WEB_ROOT = APP_ROOT / "static"


def _find_cluster_bundle() -> Path:
    candidates = [
        APP_ROOT / "cluster",
        APP_ROOT / "resources" / "cluster",
        APP_ROOT.parent / "cluster",
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys._MEIPASS) / "cluster")  # type: ignore[attr-defined]
    for path in candidates:
        if path.is_dir() and (path / "submit-job.sh").exists():
            return path
    return APP_ROOT.parent / "cluster"


CLUSTER_BUNDLE = _find_cluster_bundle()

_last_heartbeat: float | None = None
_http_server: ThreadingHTTPServer | None = None


def touch_heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = time.time()


def start_idle_watchdog(server: ThreadingHTTPServer) -> None:
    global _http_server
    _http_server = server

    def watch() -> None:
        while True:
            time.sleep(5)
            cfg = load_config()
            if not cfg.get("shutdown_when_idle", True):
                continue
            idle = int(cfg.get("idle_seconds") or 20)
            if _last_heartbeat is None:
                continue
            if time.time() - _last_heartbeat > idle:
                print(f"[{APP_SLUG}] Dashboard closed — shutting down.")
                server.shutdown()
                return

    threading.Thread(target=watch, daemon=True).start()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[{APP_SLUG}] {fmt % args}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            if path == "/api/info":
                cfg = load_config()
                json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "version": __version__,
                        "dashboard_urls": dashboard_urls(cfg),
                        "listen_host": cfg.get("listen_host") or "127.0.0.1",
                        "listen_port": int(cfg.get("listen_port") or 8765),
                        "shutdown_when_idle": bool(cfg.get("shutdown_when_idle", True)),
                    },
                )
                return
            if path == "/api/version":
                json_response(self, 200, {"ok": True, "version": __version__})
                return
            if path == "/api/config":
                cfg = load_config()
                safe = {**cfg, "ssh_password": "********" if cfg.get("ssh_password") else ""}
                safe["remote_dir"] = cluster_remote_dir(cfg)
                safe["ssh_hosts"] = ssh_hosts_for(cfg)
                safe["default_cursor_bin"] = default_cursor_bin()
                json_response(self, 200, {"ok": True, "config": safe})
                return
            if path == "/api/launch-presets":
                json_response(self, 200, {"ok": True, "presets": recent_launch_presets()})
                return
            if path == "/api/setup-status":
                json_response(self, 200, {"ok": True, **get_setup_status()})
                return
            if path == "/api/defaults":
                cfg = load_config()
                defaults = {**cfg["defaults"]}
                if not defaults.get("tunnel_name"):
                    defaults["tunnel_name"] = default_tunnel_name(cfg.get("ssh_user"))
                defaults["default_cursor_bin"] = default_cursor_bin()
                json_response(self, 200, {"ok": True, **defaults})
                return
            if path == "/api/status":
                json_response(self, 200, job_status())
                return
            if path == "/api/auth/status":
                sid = parse_qs(parsed.query).get("session_id", [""])[0]
                json_response(self, 200, login_status(sid))
                return
            json_response(self, 404, {"ok": False, "error": "Not found"})
            return

        if path in ("", "/"):
            path = "/index.html"
        touch_heartbeat()
        file_path = (WEB_ROOT / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(WEB_ROOT.resolve())):
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return

        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
        }
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", types.get(file_path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = read_json(self)

        if parsed.path == "/api/config":
            cfg = load_config()
            incoming = body.get("config", body)
            for key in (
                "ssh_host",
                "ssh_hosts",
                "ssh_user",
                "ssh_port",
                "ssh_key_path",
                "remote_dir",
                "listen_host",
                "listen_port",
                "open_browser",
                "shutdown_when_idle",
                "idle_seconds",
                "redeploy_on_connect",
            ):
                if key in incoming:
                    cfg[key] = incoming[key]
            if "ssh_hosts" in incoming:
                cfg["ssh_hosts"] = ssh_hosts_for({**cfg, "ssh_hosts": incoming["ssh_hosts"]})
            if incoming.get("ssh_password") and incoming["ssh_password"] != "********":
                cfg["ssh_password"] = incoming["ssh_password"]
            if "defaults" in incoming:
                cfg["defaults"] = {**cfg.get("defaults", {}), **incoming["defaults"]}
            save_config(cfg)
            json_response(self, 200, {"ok": True, "message": "Settings saved"})
            return

        if parsed.path == "/api/disconnect":
            clear_ssh_pool()
            json_response(self, 200, {"ok": True})
            return

        if parsed.path == "/api/heartbeat":
            touch_heartbeat()
            json_response(self, 200, {"ok": True})
            return

        if parsed.path == "/api/test":
            force_deploy = bool(body.get("force_deploy"))
            json_response(self, 200, test_connection_and_setup(CLUSTER_BUNDLE, force_deploy=force_deploy))
            return

        if parsed.path == "/api/deploy":
            force = body.get("force", True)
            json_response(self, 200, deploy_cluster_scripts(CLUSTER_BUNDLE, force=force))
            return

        if parsed.path == "/api/submit":
            json_response(self, 200, submit_job(body, bundle_dir=CLUSTER_BUNDLE))
            return

        if parsed.path == "/api/stop":
            job_id = body.get("job_id")
            if job_id:
                meta = {
                    "tunnel_name": body.get("tunnel_name"),
                    "params": body.get("params"),
                }
                json_response(self, 200, stop_job(str(job_id), meta=meta))
            else:
                json_response(self, 200, stop_jobs())
            return

        if parsed.path == "/api/history/dismiss":
            job_id = body.get("job_id")
            if not job_id:
                json_response(self, 400, {"ok": False, "error": "job_id required"})
                return
            json_response(self, 200, dismiss_stopped_job(str(job_id)))
            return

        if parsed.path == "/api/auth/start":
            provider = body.get("provider") or load_config()["defaults"].get("auth_provider", "github")
            json_response(self, 200, start_login(provider, bundle_dir=CLUSTER_BUNDLE))
            return

        json_response(self, 404, {"ok": False, "error": "Not found"})


def run_server() -> None:
    cfg = load_config()
    host = cfg.get("listen_host") or "127.0.0.1"
    port = int(cfg.get("listen_port") or 8765)
    server = ThreadingHTTPServer((host, port), Handler)
    start_idle_watchdog(server)
    urls = dashboard_urls(cfg)
    print(f"{APP_DISPLAY_NAME} v{__version__}")
    for url in urls:
        print(f"Dashboard -> {url}")
    if host in ("0.0.0.0", "::"):
        print("Listening on all interfaces (LAN/phone can use your PC IP above).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    run_server()
