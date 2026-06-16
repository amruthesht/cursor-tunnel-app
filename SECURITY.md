# Security

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.0.x   | Yes       |

## Overview

Cursor Tunnel App runs locally on your machine. It SSHs to a login node and submits Slurm jobs that run the Cursor CLI. It is not a hosted service.

## Local API

Default bind address is `127.0.0.1`. Advanced settings allow `0.0.0.0`, which exposes the HTTP API on the LAN.

There is no authentication on `/api/*`. Anyone who can reach the dashboard can read or change settings and run SSH actions (deploy, submit, stop jobs, GitHub device login).

Leave `listen_host` at `127.0.0.1` unless LAN access is intentional and the network is trusted.

## Stored credentials

| OS | Path |
|----|------|
| Windows | `%APPDATA%\cursor-tunnel-app\` |
| macOS | `~/Library/Application Support/cursor-tunnel-app/` |
| Linux | `~/.config/cursor-tunnel-app/` |

SSH keys are read from the configured path, not copied into that folder. Passwords, if used, are stored in plaintext in `config.json`. SSH keys are preferable.

## SSH host keys

Paramiko uses `AutoAddPolicy` — the first connection to a new host accepts whatever key is presented. Verify fingerprints from cluster documentation if that matters for your setup.

## Cluster

Scripts deploy to `~/cursor-tunnel/` on the login node. Device login runs `cursor tunnel user login` there. During auth, `CURSOR_CLI_DISABLE_KEYCHAIN_ENCRYPT=1` is set so batch jobs do not hang on keychain prompts.

## CORS

Responses include `Access-Control-Allow-Origin: *`, which matters mainly when binding to `0.0.0.0`.
