from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

FILE_EXTENSIONS = {".csv", ".tsv", ".parquet", ".pq", ".sqlite", ".sqlite3", ".db"}
SQLITE_EXTENSIONS = {".sqlite", ".sqlite3", ".db"}
PARQUET_EXTENSIONS = {".parquet", ".pq"}


@dataclass(frozen=True)
class TableRef:
    name: str
    path: Path
    source_type: str
    sqlite_table: str | None = None


@dataclass(frozen=True)
class SchemaRef:
    database: str
    schema: str

    def full_name(self, table: str) -> str:
        return f"{self.database}.{self.schema}.{table}"


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def safe_name(value: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    if not name:
        name = "table"
    if name[0].isdigit():
        name = f"t_{name}"
    return name


def unique_name(base: str, existing: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}"
        index += 1
    existing.add(candidate)
    return candidate


def schema_ref(data_dir: Path) -> SchemaRef:
    schema = safe_name(data_dir.expanduser().resolve().name)
    if not schema:
        schema = "files"
    return SchemaRef(database="memory", schema=schema)


def sqlite_tables(path: Path) -> list[str]:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []

    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def discover_tables(data_dir: Path) -> list[TableRef]:
    root = data_dir.expanduser().resolve()
    if not root.exists():
        return []

    existing: set[str] = set()
    refs: list[TableRef] = []
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in FILE_EXTENSIONS
    )

    for path in files:
        suffix = path.suffix.lower()
        relative_stem = safe_name(str(path.relative_to(root).with_suffix("")))
        if suffix in SQLITE_EXTENSIONS:
            db_name = safe_name(path.stem)
            for table in sqlite_tables(path):
                name = unique_name(f"{db_name}_{safe_name(table)}", existing)
                refs.append(
                    TableRef(
                        name=name,
                        path=path,
                        source_type="sqlite",
                        sqlite_table=table,
                    )
                )
            continue

        source_type = "parquet" if suffix in PARQUET_EXTENSIONS else "csv"
        refs.append(
            TableRef(
                name=unique_name(relative_stem, existing),
                path=path,
                source_type=source_type,
            )
        )

    return refs


def configure_connection(
    connection: duckdb.DuckDBPyConnection,
    data_dir: Path,
) -> list[TableRef]:
    refs = discover_tables(data_dir)
    sqlite_aliases: dict[Path, str] = {}
    namespace = schema_ref(data_dir)

    connection.execute(
        f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(namespace.schema)}"
    )

    for ref in refs:
        if ref.source_type == "sqlite":
            if ref.path not in sqlite_aliases:
                alias = safe_name(ref.path.stem)
                sqlite_aliases[ref.path] = alias
                connection.execute(
                    f"ATTACH {quote_literal(ref.path)} AS {quote_identifier(alias)} "
                    "(TYPE sqlite, READ_ONLY)"
                )
            alias = sqlite_aliases[ref.path]
            sqlite_source = (
                f"SELECT * FROM {quote_identifier(alias)}."
                f"{quote_identifier(ref.sqlite_table or '')}"
            )
            connection.execute(
                f"CREATE OR REPLACE VIEW {quote_identifier(ref.name)} AS "
                f"{sqlite_source}"
            )
            connection.execute(
                f"CREATE OR REPLACE VIEW "
                f"{quote_identifier(namespace.schema)}.{quote_identifier(ref.name)} AS "
                f"{sqlite_source}"
            )
            continue

        reader = "read_parquet" if ref.source_type == "parquet" else "read_csv_auto"
        options = ", delim='\\t'" if ref.path.suffix.lower() == ".tsv" else ""
        source_sql = f"SELECT * FROM {reader}({quote_literal(ref.path)}{options})"
        connection.execute(
            f"CREATE OR REPLACE VIEW {quote_identifier(ref.name)} AS {source_sql}"
        )
        connection.execute(
            f"CREATE OR REPLACE VIEW "
            f"{quote_identifier(namespace.schema)}.{quote_identifier(ref.name)} AS "
            f"{source_sql}"
        )

    return refs


def column_schema(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"DESCRIBE SELECT * FROM {quote_identifier(table_name)} LIMIT 0"
    ).fetchall()
    columns: list[dict[str, Any]] = []
    for row in rows:
        columns.append(
            {
                "name": row[0],
                "type": row[1],
                "kind": "COLUMN",
                "null?": "Y" if row[2] == "YES" else "N",
                "default": None,
                "primary key": "N",
                "unique key": "N",
                "check": None,
                "expression": None,
                "comment": None,
            }
        )
    return columns


def table_schemas(data_dir: Path) -> dict[str, dict[str, Any]]:
    connection = duckdb.connect(database=":memory:")
    try:
        refs = configure_connection(connection, data_dir)
        namespace = schema_ref(data_dir)
        schemas: dict[str, dict[str, Any]] = {}
        for ref in refs:
            columns = column_schema(connection, ref.name)
            qualified_schema = {
                "database": namespace.database,
                "schema": namespace.schema,
                "tableName": ref.name,
                "kind": "VIEW",
                "columns": columns,
                "column_count": len(columns),
            }
            alias_schema = {
                **qualified_schema,
                "database": ref.name,
                "schema": "",
            }
            schemas[ref.name] = alias_schema
            schemas[namespace.full_name(ref.name)] = qualified_schema
        return schemas
    finally:
        connection.close()
