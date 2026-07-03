# OpenBB Duck

![OpenBB Duck](https://github.com/user-attachments/assets/5ede5181-ce42-4f8a-9f5c-1896b9189463)

OpenBB Workspace connector for querying explicit DuckDB-readable sources.

## Install

```bash
uv tool install git+https://github.com/piiq/openbb-duck.git
```

## Run

Pass one or more sources explicitly.

```bash
openbb-duck --source './exports/*.parquet'
openbb-duck --source './exports/**/*.csv'
openbb-duck --source prices=./prices.parquet
openbb-duck --source duck=duckdb:./warehouse.db
openbb-duck --source warehouse=./warehouse.duckdb
openbb-duck --source portfolio=sqlite:./portfolio.db
openbb-duck --source lake=ducklake:metadata.ducklake
openbb-duck --source 's3://bucket/path/**/*.parquet'
```

Use `alias=source` for stable SQL names.
Since the `.db` extension is ambiguous, use `duckdb:./file.db` or `sqlite:./file.db` to specify the type of the database.

Pass `--cors-origin` multiple times to replace the default OpenBB Workspace CORS allowlist.

CLI options can also be configured with environment variables. Priority is CLI argument, then environment variable, then default.

| CLI option | Environment variable |
| --- | --- |
| `--source` | `OPENBB_DUCK_SOURCES` |
| `--host` | `OPENBB_DUCK_HOST` |
| `--port` | `OPENBB_DUCK_PORT` |
| `--reload` / `--no-reload` | `OPENBB_DUCK_RELOAD` |
| `--cors-origin` | `OPENBB_DUCK_CORS_ORIGINS` |

`OPENBB_DUCK_SOURCES` accepts a comma-separated source list.
`OPENBB_DUCK_CORS_ORIGINS` accepts a comma-separated origin list.

## Workspace Endpoints

- `GET /widgets.json` exposes one `ssrm_advanced` SQL widget.
- `GET /apps.json` exposes a minimal app template.
- `GET /table-schemas` returns registered source metadata for SQL autocomplete.
- `GET /semantic-views` returns `{}`.
- `POST /query` executes read-only SQL and returns SSRM `rowData` and `rowCount`.

Supported local source suffixes are `.csv`, `.tsv`, `.parquet`, `.pq`, `.duckdb`, `.sqlite`, and `.sqlite3`. Use `duckdb:` or `sqlite:` for `.db`.

## Development

```bash
uv run pytest
uv run pytest --e2e
uv run ruff check .
uv run ty check
```

The e2e tests create temporary CSV, TSV, Parquet, DuckDB, SQLite, and DuckLake assets under pytest's temp directory. They are optional and are not part of CI.
