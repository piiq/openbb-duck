import sqlite3
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from openbb_duck.app import create_app

pytestmark = pytest.mark.e2e


def make_csv_asset(path: Path) -> None:
    """Create a text CSV fixture in tmp_path so flat-file e2e tests stay local."""
    path.write_text(
        "symbol,price,sector\n"
        "AAPL,150,Technology\n"
        "MSFT,350,Technology\n"
        "JPM,195,Financial\n",
        encoding="utf-8",
    )


def make_tsv_asset(path: Path) -> None:
    """Create a TSV fixture because TSV uses a separate DuckDB reader option."""
    path.write_text(
        "symbol\tquantity\n"
        "AAPL\t10\n"
        "MSFT\t5\n",
        encoding="utf-8",
    )


def make_parquet_asset(path: Path) -> None:
    """Create Parquet with DuckDB so e2e coverage avoids checked-in binaries."""
    connection = duckdb.connect(database=":memory:")
    path_sql = str(path).replace("'", "''")
    try:
        connection.execute(
            "CREATE TABLE prices (symbol VARCHAR, price DOUBLE, sector VARCHAR)"
        )
        connection.execute(
            "INSERT INTO prices VALUES "
            "('AAPL', 150.0, 'Technology'), "
            "('MSFT', 350.0, 'Technology'), "
            "('JPM', 195.0, 'Financial')"
        )
        connection.execute(f"COPY prices TO '{path_sql}' (FORMAT PARQUET)")
    finally:
        connection.close()


def make_duckdb_asset(path: Path) -> None:
    """Create a real DuckDB file so e2e coverage does not commit binary fixtures."""
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE project_files (path VARCHAR, byte_count INTEGER)"
        )
        connection.execute(
            "INSERT INTO project_files VALUES "
            "('README.md', 1200), "
            "('src/openbb_duck/app.py', 4200)"
        )
    finally:
        connection.close()


def make_sqlite_asset(path: Path) -> None:
    """Create a real SQLite file for testing DuckDB's sqlite attachment path."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE positions (symbol TEXT, quantity INTEGER)")
        connection.execute("INSERT INTO positions VALUES ('AAPL', 10)")
        connection.execute("INSERT INTO positions VALUES ('MSFT', 5)")
        connection.commit()
    finally:
        connection.close()


def make_ducklake_asset(metadata_path: Path, data_path: Path) -> None:
    """Create DuckLake metadata and data files through DuckDB's DuckLake extension."""
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute("INSTALL ducklake")
        connection.execute("LOAD ducklake")
        connection.execute(
            f"ATTACH 'ducklake:{metadata_path}' AS lake "
            f"(DATA_PATH '{data_path}')"
        )
        connection.execute(
            "CREATE TABLE lake.main.lake_files "
            "(path VARCHAR, byte_count INTEGER)"
        )
        connection.execute(
            "INSERT INTO lake.main.lake_files VALUES "
            "('data/exports/filtered.parquet', 900), "
            "('data/exports/raw.parquet', 1700)"
        )
    finally:
        connection.close()


def test_csv_source_exposes_schema_and_query(tmp_path):
    csv_path = tmp_path / "prices.csv"
    make_csv_asset(csv_path)
    client = TestClient(create_app([f"prices={csv_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM prices ORDER BY symbol"},
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "prices" in schemas
    assert "memory.main.prices" in schemas
    assert [column["name"] for column in schemas["prices"]["columns"]] == [
        "symbol",
        "price",
        "sector",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"symbol": "AAPL"},
        {"symbol": "JPM"},
        {"symbol": "MSFT"},
    ]


def test_tsv_source_exposes_schema_and_query(tmp_path):
    tsv_path = tmp_path / "positions.tsv"
    make_tsv_asset(tsv_path)
    client = TestClient(create_app([f"positions={tsv_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM positions ORDER BY symbol"},
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "positions" in schemas
    assert "memory.main.positions" in schemas
    assert [column["name"] for column in schemas["positions"]["columns"]] == [
        "symbol",
        "quantity",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"symbol": "AAPL"},
        {"symbol": "MSFT"},
    ]


def test_parquet_source_exposes_schema_and_query(tmp_path):
    parquet_path = tmp_path / "prices.parquet"
    make_parquet_asset(parquet_path)
    client = TestClient(create_app([f"prices={parquet_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM prices WHERE price > 180 ORDER BY symbol"},
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "prices" in schemas
    assert "memory.main.prices" in schemas
    assert [column["name"] for column in schemas["prices"]["columns"]] == [
        "symbol",
        "price",
        "sector",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"symbol": "JPM"},
        {"symbol": "MSFT"},
    ]


def test_duckdb_source_exposes_short_alias_schema_and_query(tmp_path):
    duckdb_path = tmp_path / "openbb_duck_project.duckdb"
    make_duckdb_asset(duckdb_path)
    client = TestClient(create_app([f"project={duckdb_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={
            "query": (
                "SELECT path FROM project_files "
                "WHERE byte_count > 1000 ORDER BY path"
            )
        },
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "project_files" in schemas
    assert "project.main.project_files" in schemas
    assert [column["name"] for column in schemas["project_files"]["columns"]] == [
        "path",
        "byte_count",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"path": "README.md"},
        {"path": "src/openbb_duck/app.py"},
    ]


def test_sqlite_source_exposes_short_alias_schema_and_query(tmp_path):
    sqlite_path = tmp_path / "portfolio.sqlite"
    make_sqlite_asset(sqlite_path)
    client = TestClient(create_app([f"portfolio=sqlite:{sqlite_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM positions ORDER BY symbol"},
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "positions" in schemas
    assert "portfolio.main.positions" in schemas
    assert [column["name"] for column in schemas["positions"]["columns"]] == [
        "symbol",
        "quantity",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"symbol": "AAPL"},
        {"symbol": "MSFT"},
    ]


def test_ducklake_source_exposes_short_alias_schema_and_query(tmp_path):
    metadata_path = tmp_path / "project.ducklake"
    data_path = tmp_path / "ducklake_data"
    make_ducklake_asset(metadata_path, data_path)
    client = TestClient(create_app([f"lake=ducklake:{metadata_path}"]))

    schemas_response = client.get("/table-schemas")
    query_response = client.post(
        "/query",
        json={"query": "SELECT path FROM lake_files ORDER BY path"},
    )

    assert schemas_response.status_code == 200
    schemas = schemas_response.json()
    assert "lake_files" in schemas
    assert "lake.main.lake_files" in schemas
    assert [column["name"] for column in schemas["lake_files"]["columns"]] == [
        "path",
        "byte_count",
    ]
    assert query_response.status_code == 200
    assert query_response.json()["rowData"] == [
        {"path": "data/exports/filtered.parquet"},
        {"path": "data/exports/raw.parquet"},
    ]
