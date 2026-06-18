#!/usr/bin/env python3
"""Verify Gradle mipmap icons match resources/ before packaging."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "resources"

PAIRS = (
    ("square-icon-48.png", "mipmap-mdpi/ic_launcher.png"),
    ("square-icon-72.png", "mipmap-hdpi/ic_launcher.png"),
    ("square-icon-96.png", "mipmap-xhdpi/ic_launcher.png"),
    ("square-icon-144.png", "mipmap-xxhdpi/ic_launcher.png"),
    ("square-icon-192.png", "mipmap-xxxhdpi/ic_launcher.png"),
    ("round-icon-48.png", "mipmap-mdpi/ic_launcher_round.png"),
    ("adaptive-icon-108.png", "mipmap-mdpi/ic_launcher_foreground.png"),
    ("square-icon-320.png", "mipmap-mdpi/splash.png"),
)


def find_gradle_res() -> Path:
    matches = list(ROOT.glob("build/**/android/gradle/app/src/main/res"))
    if not matches:
        raise FileNotFoundError("Gradle res/ directory not found under build/")
    return matches[0]


def main() -> int:
    try:
        gradle_res = find_gradle_res()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    bad = []
    for src_name, rel in PAIRS:
        src = RESOURCES / src_name
        dest = gradle_res / rel
        if not src.is_file():
            bad.append(f"missing source {src}")
            continue
        if not dest.is_file():
            bad.append(f"missing gradle icon {dest}")
            continue
        if src.read_bytes() != dest.read_bytes():
            bad.append(f"icon mismatch for {rel}")

    if bad:
        print("ERROR: Gradle launcher icons are not installed correctly:", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"OK: Gradle launcher icons match resources/ ({len(PAIRS)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
