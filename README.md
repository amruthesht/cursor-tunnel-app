# Cursor Tunnel App

SSH to a Slurm login node, submit a job, and run a Cursor remote tunnel on a compute node.

## Download

Pre-built apps are on [GitHub Releases](https://github.com/amruthesht/cursor-tunnel-app/releases) when I publish them:

| Platform | File |
|----------|------|
| Windows | `CursorTunnelApp.exe` |
| macOS | `CursorTunnelApp-macos-arm64.zip` (Apple Silicon) — [details](platforms/macos/README.md) |
| Linux | `CursorTunnelApp-linux-x86_64.tar.gz` — [details](platforms/linux/README.md) |
| Android | `CursorTunnelApp-android.apk` — [details](platforms/android/README.md) |

Double-click (or run) the app; the dashboard opens at `http://127.0.0.1:8765/`. No Python required for these builds.

Settings are stored in `%APPDATA%\cursor-tunnel-app\` on Windows, `~/Library/Application Support/cursor-tunnel-app/` on macOS, and `~/.config/cursor-tunnel-app/` on Linux.

## From source

```bash
git clone https://github.com/amruthesht/cursor-tunnel-app.git
cd cursor-tunnel-app
python -m pip install -r requirements.txt
python app/main.py
```

Or use a platform launcher:

| Platform | Script |
|----------|--------|
| Windows | `platforms\windows\CursorTunnelApp.cmd` |
| Linux | `platforms/linux/CursorTunnelApp.sh` |
| macOS | `platforms/macos/CursorTunnelApp.command` |
| Android | [platforms/android/README.md](platforms/android/README.md) |

Build scripts for standalone apps live under `platforms/*/build-*`.

## Requirements

- A browser and SSH access to the cluster (VPN if your site requires it)
- Slurm on the cluster
- The [Cursor CLI](cluster/README.md) on the cluster — installed automatically at the path you configure (default `~/cursor-tunnel/cursor`) if missing

## Usage

1. **Connect** — login node, username, SSH key or password
2. **Launch** — CPUs, memory, wall time, tunnel name
3. **Running** — register on GitHub if needed, then open the tunnel in Cursor → Remote-Tunnels

The host dropdown includes ASU Sol and Phoenix login nodes; use Custom for other clusters.

## Security

[SECURITY.md](SECURITY.md). Leave the dashboard on `127.0.0.1` unless LAN access is intentional.

## Status

Pre-release (`0.0.0`). [CHANGELOG.md](CHANGELOG.md).

MIT — [LICENSE](LICENSE).
