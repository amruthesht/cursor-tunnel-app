#!/usr/bin/env python3
"""Fail if required Android Python modules are missing from the APK bundle."""

from __future__ import annotations

import io
import sys
import zipfile

REQUIRED = (
    "app/android_ui.pyc",
    "app/platform_detect.pyc",
    "app/ssh_keys.pyc",
    "app/resources/cluster/submit-job.sh",
    "app/static/index.html",
)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} path/to/app.apk", file=sys.stderr)
        return 2

    apk_path = sys.argv[1]
    with zipfile.ZipFile(apk_path) as zf:
        imy_name = "assets/chaquopy/app.imy"
        if imy_name not in zf.namelist():
            print(f"ERROR: missing {imy_name} in APK", file=sys.stderr)
            return 1
        with zipfile.ZipFile(io.BytesIO(zf.read(imy_name))) as imy:
            names = set(imy.namelist())

    missing = [path for path in REQUIRED if path not in names]
    if missing:
        print("ERROR: APK bundle is missing required Android app files:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    print(f"OK: Android bundle contains {len(REQUIRED)} required files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
