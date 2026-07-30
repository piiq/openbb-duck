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
openbb-duck --source remote=quack:localhost
openbb-duck --source 'lake=s3://bucket/prefix/**/*.parquet'
openbb-duck --source 'lake=s3://bucket/prefix/**/*.parquet' --s3-endpoint account.r2.cloudflarestorage.com --s3-access-key-id key --s3-secret-access-key secret
openbb-duck --source 's3://bucket/path/**/*.parquet'
```

Use `alias=source` for stable SQL names.
Since the `.db` extension is ambiguous, use `duckdb:./file.db` or `sqlite:./file.db` to specify the type of the database.

Pass `--cors-origin` multiple times to replace the default OpenBB Workspace CORS allowlist.
Set `OPENBB_DUCK_API_TOKEN` to require that token as an HTTP bearer token on all API endpoints. Leave it unset to disable authentication. Configure the Workspace backend with an `Authorization: Bearer <token>` header.
Pass `--quack-token` or `OPENBB_DUCK_QUACK_TOKEN` when Quack remote sources require token authentication.
Quack support is experimental until DuckDB 2.0 and may change with DuckDB releases.
For private S3-compatible object storage, set `OPENBB_DUCK_S3_ENDPOINT`, `OPENBB_DUCK_S3_ACCESS_KEY_ID`, and `OPENBB_DUCK_S3_SECRET_ACCESS_KEY`. `OPENBB_DUCK_S3_REGION` defaults to `auto`; `OPENBB_DUCK_S3_URL_STYLE` defaults to `path`.

CLI options can also be configured with environment variables. Priority is CLI argument, then environment variable, then default.

| CLI option | Environment variable |
| --- | --- |
| `--source` | `OPENBB_DUCK_SOURCES` |
| `--host` | `OPENBB_DUCK_HOST` |
| `--port` | `OPENBB_DUCK_PORT` |
| `--reload` / `--no-reload` | `OPENBB_DUCK_RELOAD` |
| `--cors-origin` | `OPENBB_DUCK_CORS_ORIGINS` |
| — | `OPENBB_DUCK_API_TOKEN` |
| `--quack-token` | `OPENBB_DUCK_QUACK_TOKEN` |
| `--s3-endpoint` | `OPENBB_DUCK_S3_ENDPOINT` |
| `--s3-access-key-id` | `OPENBB_DUCK_S3_ACCESS_KEY_ID` |
| `--s3-secret-access-key` | `OPENBB_DUCK_S3_SECRET_ACCESS_KEY` |
| `--s3-region` | `OPENBB_DUCK_S3_REGION` |
| `--s3-url-style` | `OPENBB_DUCK_S3_URL_STYLE` |

`OPENBB_DUCK_SOURCES` accepts a comma-separated source list.
`OPENBB_DUCK_CORS_ORIGINS` accepts a comma-separated origin list.

## Workspace Endpoints

- `GET /widgets.json` exposes one `ssrm_advanced` SQL widget.
- `GET /apps.json` exposes a minimal app template.
- `GET /table-schemas` returns registered source metadata for SQL autocomplete.
- `GET /semantic-views` returns `{}`.
- `POST /query` executes read-only SQL and returns SSRM `rowData` and `rowCount`.

Supported local source suffixes are `.csv`, `.tsv`, `.parquet`, `.pq`, `.duckdb`, `.sqlite`, and `.sqlite3`. Use `duckdb:` or `sqlite:` for `.db`. Quack remote sources use the `quack:` URI scheme.

## Development

```bash
uv run pytest
uv run pytest --e2e
uv run ruff check .
uv run ty check
```

The e2e tests create temporary CSV, TSV, Parquet, DuckDB, SQLite, and DuckLake assets under pytest's temp directory. They are optional and are not part of CI.
