# Linux

## Releases

`CursorTunnelApp-linux-x86_64.tar.gz` from [Releases](https://github.com/amruthesht/cursor-tunnel-app/releases):

```bash
tar xzf CursorTunnelApp-linux-x86_64.tar.gz
./CursorTunnelApp
```

Opens `http://127.0.0.1:8765/`. Release builds are x86_64; on ARM, use `CursorTunnelApp.sh` from a clone or run `build-app.sh` on that machine.

## Source

```bash
chmod +x platforms/linux/CursorTunnelApp.sh
./platforms/linux/CursorTunnelApp.sh
```

Python 3.10+ and a repo clone. Config: `~/.config/cursor-tunnel-app/config.json`. Log: `~/.config/cursor-tunnel-app/cursor-tunnel-app.log`.

## Building

`platforms/linux/build-app.sh` → `dist/CursorTunnelApp` and `dist/CursorTunnelApp-linux-<arch>.tar.gz`.

## Desktop entry

```ini
[Desktop Entry]
Name=Cursor Tunnel App
Exec=/path/to/CursorTunnelApp
Type=Application
Terminal=false
Categories=Network;
```
