# macOS

## Releases

`CursorTunnelApp-macos-arm64.zip` from [Releases](https://github.com/amruthesht/cursor-tunnel-app/releases) → unzip → move `CursorTunnelApp.app` to Applications → open. Apple Silicon builds; Intel Macs can use source or build locally.

### Gatekeeper

Unsigned app — if macOS blocks it: right-click → Open, or System Settings → Privacy & Security → Open Anyway, or:

```bash
xattr -dr com.apple.quarantine /Applications/CursorTunnelApp.app
```

## Source

Python 3.10+ from [python.org](https://www.python.org/downloads/macos/), then from the repo root:

```bash
chmod +x platforms/macos/CursorTunnelApp.command
./platforms/macos/CursorTunnelApp.command
```

Config: `~/Library/Application Support/cursor-tunnel-app/config.json`. Log (source launcher): `~/Library/Application Support/cursor-tunnel-app/cursor-tunnel-app.log`. The `.app` from Releases uses the same config folder.

## Building

`platforms/macos/build-app.sh` → `dist/CursorTunnelApp.app` and `dist/CursorTunnelApp-macos-arm64.zip`. Build on the Mac it will run on.
