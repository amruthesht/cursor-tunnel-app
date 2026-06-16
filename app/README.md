# App

HTTP server and web dashboard used by every platform build.

```
app/
  main.py, server.py, ssh_client.py
  config_store.py, tunnel_history.py, slurm_time.py
  static/     Connect / Running / Launch UI
```

Dev: `pip install -r requirements.txt && python app/main.py` → `http://127.0.0.1:8765/`

| Method | Path |
|--------|------|
| GET | `/api/config` |
| POST | `/api/config` |
| POST | `/api/test` |
| POST | `/api/deploy` |
| POST | `/api/submit` |
| GET | `/api/status` |
| POST | `/api/stop` |
| GET | `/api/info` |

Config directory paths are in the root [README](../README.md).

Platform scripts: [platforms/](../platforms/README.md).
