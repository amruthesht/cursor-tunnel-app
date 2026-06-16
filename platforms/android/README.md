# Android

Same dashboard and backend as desktop — Connect, Launch, Running, GitHub registration, timers, stop/rerun.

## Install

`CursorTunnelApp-android.apk` from [Releases](https://github.com/amruthesht/cursor-tunnel-app/releases) when available. Sideload (enable install from unknown sources). Cluster VPN on the phone before Connect. SSH credentials and the Cursor CLI on the cluster are still required.

## On the phone

Connect → Launch → Register on GitHub on the running card → use the tunnel name in desktop Cursor (Remote-Tunnels). SSH key path points to a file on the device, or use password auth. Outdated cluster scripts: Connect → Advanced → Re-deploy scripts.

## Building the APK

Needs Linux or WSL (not Windows Python alone):

```bash
chmod +x platforms/android/build-apk.sh
./platforms/android/build-apk.sh
```

First run downloads the Android SDK (~1 GB); can take 30+ minutes. Output: `dist/CursorTunnelApp-android.apk`.

WSL on Windows: install Ubuntu (`wsl --install -d Ubuntu`), then run the script from `/mnt/c/.../cursor-tunnel-app`.
