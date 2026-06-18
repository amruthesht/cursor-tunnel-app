"""Detect Briefcase/Chaquopy Android runtime."""

from __future__ import annotations

import sys


def is_android() -> bool:
    if sys.platform == "android":
        return True
    if hasattr(sys, "getandroidapilevel"):
        return True
    try:
        from org.beeware.android import MainActivity  # noqa: F401

        return True
    except ImportError:
        return False
