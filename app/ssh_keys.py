"""SSH key pair stored in app private storage (app config dir / ssh)."""

from __future__ import annotations

import os
from pathlib import Path

from config_store import app_config_dir, load_config, save_config

KEY_COMMENT = "cursor-tunnel-app"
PRIVATE_NAME = "id_ed25519"
PUBLIC_NAME = "id_ed25519.pub"


def ssh_dir() -> Path:
    path = app_config_dir() / "ssh"
    path.mkdir(parents=True, exist_ok=True)
    return path


def private_key_path() -> Path:
    return ssh_dir() / PRIVATE_NAME


def public_key_path() -> Path:
    return ssh_dir() / PUBLIC_NAME


def key_exists() -> bool:
    return private_key_path().is_file()


def read_public_key() -> str:
    path = public_key_path()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def key_status() -> dict:
    priv = private_key_path()
    return {
        "exists": priv.is_file(),
        "private_path": str(priv),
        "public_path": str(public_key_path()),
        "public_key": read_public_key(),
    }


def _write_key_files(private_pem: bytes, public_line: str) -> None:
    priv = private_key_path()
    pub = public_key_path()
    priv.write_bytes(private_pem)
    pub.write_text(public_line.rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(priv, 0o600)
        os.chmod(pub, 0o644)
    except OSError:
        pass


def _ensure_config_points_at_key() -> str:
    path = str(private_key_path())
    cfg = load_config()
    if cfg.get("ssh_key_path") != path:
        cfg["ssh_key_path"] = path
        save_config(cfg)
    return path


def generate_keypair(*, force: bool = False) -> dict:
    """Create ed25519 key pair in app storage; set config ssh_key_path."""
    if key_exists() and not force:
        path = _ensure_config_points_at_key()
        return {
            "ok": True,
            "created": False,
            "private_path": path,
            "public_key": read_public_key(),
            "message": "Key already exists",
        }

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_openssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")
    public_line = f"{public_openssh} {KEY_COMMENT}"

    _write_key_files(private_pem, public_line)
    path = _ensure_config_points_at_key()
    return {
        "ok": True,
        "created": True,
        "private_path": path,
        "public_key": public_line,
        "message": "SSH key created — copy the public key to your cluster",
    }
