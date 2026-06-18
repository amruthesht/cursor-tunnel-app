"""Briefcase Android shell: WebView + background HTTP server."""

from __future__ import annotations

import socket
import threading
import time

from config_store import dashboard_urls, load_config
from java import dynamic_proxy
from org.beeware.android import IPythonApp, MainActivity
from server import run_server


def _wait_for_server(url: str, timeout_sec: float = 8.0) -> None:
    host = "127.0.0.1"
    port = int(url.rsplit(":", 1)[-1].rstrip("/"))
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)


def _mount_webview(url: str) -> None:
    from android.view import ViewGroup
    from android.webkit import WebView
    from android.widget import LinearLayout

    activity = MainActivity.singletonThis
    webview = WebView(activity)
    settings = webview.getSettings()
    settings.setJavaScriptEnabled(True)
    settings.setDomStorageEnabled(True)

    layout = LinearLayout(activity)
    layout.setOrientation(LinearLayout.VERTICAL)
    params = ViewGroup.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.MATCH_PARENT,
    )
    layout.addView(webview, params)
    activity.setContentView(layout)
    _wait_for_server(url)
    webview.loadUrl(url)


class DashboardApp(dynamic_proxy(IPythonApp)):
    """Registered with MainActivity; onCreate runs on the UI thread after boot()."""

    def __init__(self) -> None:
        super().__init__()

    def onCreate(self) -> None:
        url = dashboard_urls(load_config())[0]
        _mount_webview(url)

    def onStart(self) -> None:
        pass

    def onResume(self) -> None:
        pass

    def onActivityResult(self, request_code: int, result_code: int, data) -> None:
        pass

    def onConfigurationChanged(self, new_config) -> None:
        pass

    def onOptionsItemSelected(self, menuitem) -> bool:
        return False

    def onPrepareOptionsMenu(self, menu) -> bool:
        return False


def boot() -> None:
    """Start HTTP server and register UI hooks with Briefcase MainActivity."""
    MainActivity.setPythonApp(DashboardApp())
    threading.Thread(target=run_server, daemon=True).start()
