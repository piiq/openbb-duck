from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb

PARQUET_SUFFIXES = (".parquet", ".pq")
CSV_SUFFIXES = (".csv", ".tsv")
INFORMATION_SCHEMA_TABLES = ("columns", "tables", "schemata", "views")


def quote_identifier(value: str) -> str:
    """Quote SQL identifiers.

    DuckDB identifiers name objects, so they use double quotes and escape embedded
    double quotes. This is not interchangeable with SQL string literal quoting.
    """
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str | Path) -> str:
    """Quote SQL string literals.

    Source paths and URIs are values passed into DuckDB SQL, so they use single
    quotes and escape embedded single quotes. This is not valid for identifiers.
    """
    return "'" + str(value).replace("'", "''") + "'"


def safe_name(value: str) -> str:
    """Convert user-provided aliases and paths into stable DuckDB identifiers."""
    name = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    if not name:
        name = "source"
    if name[0].isdigit():
        name = f"t_{name}"
    return name


def configure_connection(
    connection: duckdb.DuckDBPyConnection,
    sources: list[str],
) -> None:
    """Register every explicit source on a fresh per-request DuckDB connection."""
    aliases: set[str] = set()
    for alias, target, kind in source_specs(sources):
        aliases.add(alias)

        if kind == "duckdb":
            path = target.removeprefix("duckdb:")
            connection.execute(
                f"ATTACH {quote_literal(path)} AS {quote_identifier(alias)} "
                "(READ_ONLY)"
            )
            continue

        if kind == "sqlite":
            path = target.removeprefix("sqlite:")
            connection.execute(
                f"ATTACH {quote_literal(path)} AS {quote_identifier(alias)} "
                "(TYPE sqlite, READ_ONLY)"
            )
            continue

        if kind == "ducklake":
            connection.execute("INSTALL ducklake")
            connection.execute("LOAD ducklake")
            connection.execute(
                f"ATTACH {quote_literal(target)} AS {quote_identifier(alias)}"
            )
            continue

        reader = "read_parquet" if kind == "parquet" else "read_csv_auto"
        options = (
            ", union_by_name=true, hive_partitioning=true"
            if kind == "parquet"
            else ""
        )
        if target_without_query(target).lower().endswith(".tsv"):
            options = ", delim='\\t'"
        connection.execute(
            f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS "
            f"SELECT * FROM {reader}({quote_literal(target)}{options})"
        )

    alias_attached_tables(connection, aliases)


def alias_attached_tables(
    connection: duckdb.DuckDBPyConnection,
    used_aliases: set[str],
) -> None:
    """Expose attached catalog tables as simple memory views for SQL autocomplete."""
    rows = connection.execute(
        "SELECT table_catalog, table_schema, table_name "
        "FROM information_schema.tables "
        "WHERE table_catalog != 'memory' "
        "ORDER BY table_catalog, table_schema, table_name"
    ).fetchall()
    for catalog, schema, table in rows:
        alias = safe_name(table)
        if alias in used_aliases:
            raise ValueError(f"duplicate table alias '{alias}'")
        used_aliases.add(alias)
        connection.execute(
            f"CREATE OR REPLACE VIEW {quote_identifier(alias)} AS "
            f"SELECT * FROM {quote_identifier(catalog)}."
            f"{quote_identifier(schema)}.{quote_identifier(table)}"
        )


def source_specs(sources: list[str]) -> list[tuple[str, str, str]]:
    """Parse and validate sources once for CLI startup and connection setup."""
    aliases: set[str] = set()
    specs: list[tuple[str, str, str]] = []
    for source in sources:
        alias, target = parse_source(source)
        kind = source_kind(target)
        alias = safe_name(alias or alias_from_target(target, kind))
        if alias in aliases:
            raise ValueError(f"duplicate source alias '{alias}'")
        aliases.add(alias)
        specs.append((alias, target, kind))
    return specs


def parse_source(source: str) -> tuple[str | None, str]:
    """Split optional alias=source syntax while leaving plain paths untouched."""
    alias, separator, target = source.partition("=")
    if separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias):
        return alias, target
    return None, source


def source_kind(target: str) -> str:
    """Classify explicit source strings without inspecting folders or guessing .db."""
    lower_target = target_without_query(target).lower()
    if target.startswith("duckdb:"):
        return "duckdb"
    if target.startswith("sqlite:"):
        return "sqlite"
    if target.startswith("ducklake:"):
        return "ducklake"
    if lower_target.endswith(".duckdb"):
        return "duckdb"
    if lower_target.endswith((".sqlite", ".sqlite3")):
        return "sqlite"
    if lower_target.endswith(".db"):
        raise ValueError(
            f"ambiguous source '{target}'; use duckdb:{target} or sqlite:{target}"
        )
    if lower_target.endswith(PARQUET_SUFFIXES):
        return "parquet"
    if lower_target.endswith(CSV_SUFFIXES):
        return "csv"
    raise ValueError(f"unsupported source '{target}'")


def alias_from_target(target: str, kind: str) -> str:
    """Derive aliases only when users omit alias=source for unambiguous inputs."""
    if kind in {"duckdb", "sqlite"}:
        path = target.removeprefix(f"{kind}:")
        return Path(path).stem
    if kind == "ducklake":
        return Path(target.removeprefix("ducklake:")).stem or "ducklake"

    parsed = urlparse(target)
    path = parsed.path if parsed.scheme else target
    compact = re.sub(r"[*?\[\]]+", "", path).strip("/")
    if not compact:
        compact = parsed.netloc or "source"
    path_name = Path(compact)
    return path_name.stem or path_name.parent.name or "source"


def target_without_query(target: str) -> str:
    """Ignore URI query strings when selecting a reader from the source suffix."""
    return target.split("?", 1)[0]


def table_schemas(sources: list[str]) -> dict[str, dict[str, Any]]:
    """Expose autocomplete metadata from DuckDB after all sources are registered."""
    connection = duckdb.connect(database=":memory:")
    try:
        configure_connection(connection, sources)
        rows = connection.execute(
            "SELECT table_catalog, table_schema, table_name, table_type "
            "FROM information_schema.tables "
            "ORDER BY table_catalog, table_schema, table_name"
        ).fetchall()
        schemas: dict[str, dict[str, Any]] = {}
        for catalog, schema, table, table_type in rows:
            columns = catalog_columns(connection, catalog, schema, table)
            table_schema = {
                "database": catalog,
                "schema": schema,
                "tableName": table,
                "kind": table_type,
                "columns": columns,
                "column_count": len(columns),
            }
            full_name = f"{catalog}.{schema}.{table}"
            schemas[full_name] = table_schema
            if catalog == "memory" and schema == "main":
                schemas[table] = table_schema
            if catalog == "memory" and schema == "information_schema":
                schemas[f"{schema}.{table}"] = table_schema
        schemas.update(information_schema_schemas(connection))
        return schemas
    finally:
        connection.close()


def information_schema_schemas(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, dict[str, Any]]:
    """Publish DuckDB catalog views because DuckDB omits them from table listings."""
    schemas: dict[str, dict[str, Any]] = {}
    for table in INFORMATION_SCHEMA_TABLES:
        rows = connection.execute(
            "DESCRIBE SELECT * FROM "
            f"{quote_identifier('information_schema')}.{quote_identifier(table)} "
            "LIMIT 0"
        ).fetchall()
        table_schema = {
            "database": "memory",
            "schema": "information_schema",
            "tableName": table,
            "kind": "VIEW",
            "columns": column_dicts(rows),
            "column_count": len(rows),
        }
        schemas[f"memory.information_schema.{table}"] = table_schema
        schemas[f"information_schema.{table}"] = table_schema
    return schemas


def catalog_columns(
    connection: duckdb.DuckDBPyConnection,
    catalog: str,
    schema: str,
    table: str,
) -> list[dict[str, Any]]:
    """Read column metadata once from information_schema for autocomplete output."""
    rows = connection.execute(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = ? AND table_name = ? "
        "ORDER BY ordinal_position",
        [catalog, schema, table],
    ).fetchall()
    return column_dicts(rows)


def column_dicts(rows: list[tuple]) -> list[dict[str, Any]]:
    """Format DuckDB column metadata into Terminal Pro's schema shape."""
    return [
        {
            "name": row[0],
            "type": row[1],
            "kind": "COLUMN",
            "null?": "Y" if row[2] == "YES" else "N",
            "default": row[3],
            "primary key": "N",
            "unique key": "N",
            "check": None,
            "expression": None,
            "comment": None,
        }
        for row in rows
    ]
