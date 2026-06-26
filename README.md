# OpenBB Duck

OpenBB Workspace connector for querying CSV, Parquet, and SQLite files with DuckDB.

## Install

```bash
uv tool install git+ssh://git@github.com/piiq/openbb-duck.git
```

## Run

```bash
openbb-duck --data-dir /path/to/files --host 127.0.0.1 --port 7779
```

If `--data-dir` is omitted, the backend uses the current working directory.
Pass `--cors-origin` multiple times to replace the default OpenBB Workspace CORS
allowlist.

CLI options can also be configured with environment variables. Priority is CLI
argument, then environment variable, then default.

| CLI option | Environment variable |
| --- | --- |
| `--data-dir` | `OPENBB_DUCK_DATA_DIR` |
| `--host` | `OPENBB_DUCK_HOST` |
| `--port` | `OPENBB_DUCK_PORT` |
| `--reload` / `--no-reload` | `OPENBB_DUCK_RELOAD` |
| `--cors-origin` | `OPENBB_DUCK_CORS_ORIGINS` |

`OPENBB_DUCK_CORS_ORIGINS` accepts a comma-separated origin list.

## Workspace Endpoints

- `GET /widgets.json` exposes one `ssrm_advanced` SQL widget.
- `GET /apps.json` exposes a minimal app template.
- `GET /table-schemas` returns discovered table metadata for SQL autocomplete.
- `GET /semantic-views` returns `{}`.
- `POST /query` executes read-only SQL and returns SSRM `rowData` and `rowCount`.

Supported files are `.csv`, `.tsv`, `.parquet`, `.pq`, `.sqlite`, `.sqlite3`, and `.db`.
