#!/usr/bin/env python3
"""Fail if arm64 native libs in an APK are not 16 KB page aligned (Android 15+ phones)."""

from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath

MIN_ALIGN = 0x4000  # 16 KB


def is_signed(apk_path: str) -> bool:
    data = Path(apk_path).read_bytes()
    if b"APK Sig Block 42" in data:
        return True
    with zipfile.ZipFile(apk_path) as zf:
        return any(
            n == "META-INF/MANIFEST.MF" or n.endswith((".RSA", ".DSA", ".EC"))
            for n in zf.namelist()
        )


def min_load_alignment(data: bytes) -> int | None:
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2:
        return None
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x36)[0]
    e_phnum = struct.unpack_from("<H", data, 0x38)[0]
    aligns: list[int] = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if struct.unpack_from("<I", data, off)[0] != 1:  # PT_LOAD
            continue
        aligns.append(struct.unpack_from("<Q", data, off + 0x30)[0])
    return min(aligns) if aligns else None


def iter_arm64_so_paths(zf: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for name in zf.namelist():
        if not name.endswith(".so"):
            continue
        if "/arm64-v8a/" in name or name.startswith("lib/arm64-v8a/"):
            out.append((name, zf.read(name)))
    for name in zf.namelist():
        if not name.endswith(".imy") or "arm64" not in PurePosixPath(name).name:
            continue
        with zipfile.ZipFile(zf.open(name)) as imy:
            for inner in imy.namelist():
                if inner.endswith(".so"):
                    out.append((f"{name}!{inner}", imy.read(inner)))
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} path/to/app.apk", file=sys.stderr)
        return 2

    apk_path = sys.argv[1]
    if not is_signed(apk_path):
        print(
            "ERROR: APK is not signed (Android will reject it as invalid/corrupt). "
            "Run platforms/android/build-apk.sh to sign after packaging.",
            file=sys.stderr,
        )
        return 1

    bad: list[tuple[str, int]] = []
    ok_count = 0

    with zipfile.ZipFile(apk_path) as zf:
        entries = iter_arm64_so_paths(zf)
        if not entries:
            print("ERROR: no arm64-v8a native libraries found in APK", file=sys.stderr)
            return 1
        for label, data in entries:
            align = min_load_alignment(data)
            if align is None:
                print(f"SKIP {label}: not ELF64")
                continue
            if align >= MIN_ALIGN:
                ok_count += 1
                continue
            bad.append((label, align))

    if bad:
        print("ERROR: APK is not 16 KB compatible (Android 15+ may reject install):", file=sys.stderr)
        for label, align in bad:
            print(f"  {label}: {align} byte alignment ({align // 1024} KB)", file=sys.stderr)
        if any("_rust.so" in label for label, _ in bad):
            print(
                "Hint: cryptography needs the 42.0.8-1 Chaquopy wheel "
                "(see platforms/android/build-apk.sh).",
                file=sys.stderr,
            )
        print(f"{ok_count} libs OK, {len(bad)} libs failed", file=sys.stderr)
        return 1

    print(f"OK: {ok_count} arm64 native libraries are 16 KB aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
