from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
from fastapi import HTTPException

from openbb_duck.discovery import (
    ObjectStorageConfig,
    configure_connection,
    quote_identifier,
)

READ_ONLY_PREFIXES = ("select", "with")


def normalize_read_only_query(query: str) -> str:
    """Accept only one SELECT/WITH statement before embedding it for SSRM."""
    stripped = query.strip().rstrip(";").strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Query is required")
    if ";" in stripped:
        raise HTTPException(
            status_code=400,
            detail="Only one read-only SQL statement is allowed",
        )
    if not stripped.lower().startswith(READ_ONLY_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail="Only read-only SELECT statements are allowed",
        )
    return stripped


def sql_literal(value: Any) -> str:
    """Render SSRM filter values into simple DuckDB SQL literals."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_filter(field: str, config: dict[str, Any]) -> str | None:
    """Translate one AG Grid SSRM filter config into a DuckDB WHERE predicate."""
    filter_type = config.get("filterType", "text")
    condition = config.get("type", "contains")
    column = quote_identifier(field)

    if filter_type == "set":
        values = config.get("values") or []
        if not values:
            return None
        return f"{column} IN ({', '.join(sql_literal(value) for value in values)})"

    value = config.get("filter")
    if condition == "notBlank":
        blank = "0" if filter_type == "number" else "''"
        return f"{column} IS NOT NULL AND {column} != {blank}"
    if condition == "blank":
        blank = "0" if filter_type == "number" else "''"
        return f"({column} IS NULL OR {column} = {blank})"
    if value in (None, ""):
        return None

    if filter_type == "number":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid number filter for {field}",
            ) from exc
        value_sql = str(number)
        if condition == "equals":
            return f"{column} = {value_sql}"
        if condition == "notEqual":
            return f"{column} != {value_sql}"
        if condition == "greaterThan":
            return f"{column} > {value_sql}"
        if condition == "greaterThanOrEqual":
            return f"{column} >= {value_sql}"
        if condition == "lessThan":
            return f"{column} < {value_sql}"
        if condition == "lessThanOrEqual":
            return f"{column} <= {value_sql}"
        if condition == "inRange":
            to_value = config.get("filterTo", value)
            return f"{column} BETWEEN {value_sql} AND {float(to_value)}"
        return None

    escaped = str(value).replace("'", "''")
    if condition == "contains":
        return f"{column} LIKE '%{escaped}%'"
    if condition == "notContains":
        return f"{column} NOT LIKE '%{escaped}%'"
    if condition == "equals":
        return f"{column} = {sql_literal(value)}"
    if condition == "notEqual":
        return f"{column} != {sql_literal(value)}"
    if condition == "startsWith":
        return f"{column} LIKE '{escaped}%'"
    if condition == "endsWith":
        return f"{column} LIKE '%{escaped}'"
    return None


def build_where(filters: dict[str, Any] | None) -> str:
    """Join SSRM filters for the wrapper query that paginates Terminal Pro results."""
    clauses = [
        clause
        for field, config in (filters or {}).items()
        if (clause := build_filter(field, config))
    ]
    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def build_order(sort_model: list[dict[str, Any]] | None) -> str:
    """Translate AG Grid sort model entries into an ORDER BY clause."""
    parts: list[str] = []
    for item in sort_model or []:
        field = item.get("colId")
        direction = str(item.get("sort", "asc")).upper()
        if not field:
            continue
        if direction not in {"ASC", "DESC"}:
            direction = "ASC"
        parts.append(f"{quote_identifier(field)} {direction}")
    return f" ORDER BY {', '.join(parts)}" if parts else ""


def serialize_value(value: Any) -> Any:
    """Convert DuckDB values into JSON-safe values for FastAPI responses."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def rows_from_cursor(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return cursor rows as dictionaries because SSRM expects row objects."""
    columns = [column[0] for column in cursor.description or []]
    return [
        {column: serialize_value(value) for column, value in zip(columns, row)}
        for row in cursor.fetchall()
    ]


def execute_ssrm_query(
    sources: list[str],
    request: dict[str, Any],
    quack_token: str | None = None,
    object_storage: ObjectStorageConfig | None = None,
) -> dict[str, Any]:
    """Run a read-only user query after registering configured sources."""
    query = normalize_read_only_query(request.get("query", "SELECT 1"))
    start = int(request.get("startRow") or 0)
    end = int(request.get("endRow") or start + 500)
    limit = max(end - start, 0)

    where_sql = build_where(request.get("filterModel"))
    order_sql = build_order(request.get("sortModel"))

    base = f"({query}) AS base_query"
    count_sql = (
        "SELECT COUNT(*) AS row_count FROM "
        f"(SELECT * FROM {base}{where_sql}) AS counted"
    )
    data_sql = (
        f"SELECT * FROM {base}{where_sql}{order_sql} "
        f"LIMIT {limit} OFFSET {start}"
    )

    connection = duckdb.connect(database=":memory:")
    try:
        configure_connection(
            connection,
            sources,
            quack_token=quack_token,
            object_storage=object_storage,
        )
        count_row = connection.execute(count_sql).fetchone()
        if count_row is None:
            raise HTTPException(status_code=500, detail="Count query returned no rows")
        row_count = count_row[0]
        cursor = connection.execute(data_sql)
        return {
            "rowData": rows_from_cursor(cursor),
            "rowCount": row_count,
            "lastRow": row_count if end >= row_count else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        connection.close()
