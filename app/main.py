#!/usr/bin/env python3
"""Entry point — opens dashboard and runs local API."""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure app dir is on path when frozen or run from repo root
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config_store import dashboard_urls, load_config  # noqa: E402
from server import run_server  # noqa: E402


def open_browser_later() -> None:
    cfg = load_config()
    if not cfg.get("open_browser", True):
        return
    # pythonw.exe (background mode) cannot open browsers reliably on Windows
    if Path(sys.executable).name.lower() == "pythonw.exe":
        return
    urls = dashboard_urls(cfg)
    time.sleep(0.8)
    webbrowser.open(urls[0])


def main() -> None:
    from platform_detect import is_android

    if is_android():
        from android_ui import boot

        boot()
        return

    threading.Thread(target=open_browser_later, daemon=True).start()
    run_server()


if __name__ == "__main__":
    main()
