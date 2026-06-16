"""Short-lived status for long-running cluster setup (Cursor CLI install)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_state = {"active": False, "phase": "idle", "message": ""}


def set_setup_status(phase: str, message: str) -> None:
    with _lock:
        _state["active"] = True
        _state["phase"] = phase
        _state["message"] = message


def clear_setup_status() -> None:
    with _lock:
        _state["active"] = False
        _state["phase"] = "idle"
        _state["message"] = ""


def get_setup_status() -> dict:
    with _lock:
        return dict(_state)
