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

## Workspace Endpoints

- `GET /widgets.json` exposes one `ssrm_advanced` SQL widget.
- `GET /apps.json` exposes a minimal app template.
- `GET /table-schemas` returns discovered table metadata for SQL autocomplete.
- `GET /semantic-views` returns `{}`.
- `POST /query` executes read-only SQL and returns SSRM `rowData` and `rowCount`.

Supported files are `.csv`, `.tsv`, `.parquet`, `.pq`, `.sqlite`, `.sqlite3`, and `.db`.
