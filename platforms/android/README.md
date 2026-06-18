# Android

Same dashboard and backend as desktop — Connect, Launch, Running, GitHub registration, timers, stop/rerun.

## Install

`CursorTunnelApp-android.apk` from [Releases](https://github.com/amruthesht/cursor-tunnel-app/releases) when available. Sideload (enable install from unknown sources). Cluster VPN on the phone before Connect. SSH credentials and the Cursor CLI on the cluster are still required.

## On the phone

Connect → Launch → Register on GitHub on the running card → use the tunnel name in desktop Cursor (Remote-Tunnels). Cluster VPN before Connect.

**SSH key (one-time setup):**

1. Connect tab → **Generate SSH key** (stored privately in this app).
2. **Copy public key** → on the cluster, add that line to `~/.ssh/authorized_keys` (see below).
3. Enter username → **Connect** (password can stay empty).

The private key stays in the app’s private storage. It is removed only if you uninstall the app or clear its data. Or use password auth instead of a key.

Outdated cluster scripts: Connect → Advanced → Re-deploy scripts.

### Add public key on Sol (once)

From a PC that already SSHs to Sol:

```bash
ssh YOUR_ASURITE@login.sol.rc.asu.edu
mkdir -p ~/.ssh && chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys   # paste the line you copied from the app
chmod 600 ~/.ssh/authorized_keys
```

Or paste the copied line in any existing SSH session to the login node.

## Building the APK

Needs Linux or WSL (not Windows Python alone):

```bash
chmod +x platforms/android/build-apk.sh
./platforms/android/build-apk.sh
```

First run downloads the Android SDK (~1 GB); can take 30+ minutes. Output: `dist/CursorTunnelApp-android.apk`.

WSL on Windows: install Ubuntu (`wsl --install -d Ubuntu`), then run the script from `/mnt/c/.../cursor-tunnel-app`.
