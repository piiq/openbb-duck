import sqlite3

import duckdb
import pytest
from fastapi.testclient import TestClient

from openbb_duck.app import create_app
from openbb_duck.discovery import configure_connection


def write_csv(path):
    path.write_text(
        "symbol,price,sector\n"
        "AAPL,150,Technology\n"
        "MSFT,350,Technology\n"
        "JPM,195,Financial\n",
        encoding="utf-8",
    )


def write_sqlite(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE positions (symbol TEXT, quantity INTEGER)")
    conn.execute("INSERT INTO positions VALUES ('AAPL', 10)")
    conn.commit()
    conn.close()


def write_duckdb(path):
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE holdings (symbol VARCHAR, quantity INTEGER)")
    conn.execute("INSERT INTO holdings VALUES ('MSFT', 5)")
    conn.close()


def test_widgets_expose_source_backed_default_query(tmp_path):
    csv_path = tmp_path / "prices.csv"
    write_csv(csv_path)
    client = TestClient(create_app([f"prices={csv_path}"]))

    response = client.get("/widgets.json")

    assert response.status_code == 200
    widgets = response.json()
    assert list(widgets) == ["duck_sql"]
    assert widgets["duck_sql"]["type"] == "ssrm_advanced"
    assert widgets["duck_sql"]["schemaName"] == "ALL_DATABASES_ALL_SCHEMAS_ALL_TABLES"
    assert widgets["duck_sql"]["params"][0]["language"] == "sql"
    assert (
        widgets["duck_sql"]["params"][0]["value"]
        == 'SELECT * FROM "prices" LIMIT 100'
    )


def test_table_schemas_include_file_sqlite_duckdb_and_information_schema(tmp_path):
    csv_path = tmp_path / "prices.csv"
    sqlite_path = tmp_path / "portfolio.db"
    duckdb_path = tmp_path / "warehouse.duckdb"
    write_csv(csv_path)
    write_sqlite(sqlite_path)
    write_duckdb(duckdb_path)
    client = TestClient(
        create_app(
            [
                f"prices={csv_path}",
                f"portfolio=sqlite:{sqlite_path}",
                f"warehouse={duckdb_path}",
            ]
        )
    )

    response = client.get("/table-schemas")

    assert response.status_code == 200
    schemas = response.json()
    assert "prices" in schemas
    assert "memory.main.prices" in schemas
    assert "positions" in schemas
    assert "holdings" in schemas
    assert "portfolio.main.positions" in schemas
    assert "warehouse.main.holdings" in schemas
    assert "information_schema.columns" in schemas
    assert [column["name"] for column in schemas["prices"]["columns"]] == [
        "symbol",
        "price",
        "sector",
    ]
    assert [
        column["name"] for column in schemas["portfolio.main.positions"]["columns"]
    ] == ["symbol", "quantity"]
    assert [column["name"] for column in schemas["positions"]["columns"]] == [
        "symbol",
        "quantity",
    ]
    assert [
        column["name"] for column in schemas["warehouse.main.holdings"]["columns"]
    ] == ["symbol", "quantity"]
    assert [column["name"] for column in schemas["holdings"]["columns"]] == [
        "symbol",
        "quantity",
    ]
    assert {"column_name", "table_name", "table_schema"}.issubset(
        {column["name"] for column in schemas["information_schema.columns"]["columns"]}
    )


def test_query_endpoint_accepts_file_and_attached_database_sources(tmp_path):
    csv_path = tmp_path / "prices.csv"
    sqlite_path = tmp_path / "portfolio.db"
    duckdb_path = tmp_path / "warehouse.duckdb"
    write_csv(csv_path)
    write_sqlite(sqlite_path)
    write_duckdb(duckdb_path)
    client = TestClient(
        create_app(
            [
                f"prices={csv_path}",
                f"portfolio=sqlite:{sqlite_path}",
                f"warehouse={duckdb_path}",
            ]
        )
    )

    csv_response = client.post(
        "/query",
        json={"query": 'SELECT symbol FROM "prices" ORDER BY symbol'},
    )
    sqlite_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM positions"},
    )
    duckdb_response = client.post(
        "/query",
        json={"query": "SELECT symbol FROM holdings"},
    )

    assert csv_response.status_code == 200
    assert csv_response.json()["rowData"] == [
        {"symbol": "AAPL"},
        {"symbol": "JPM"},
        {"symbol": "MSFT"},
    ]
    assert sqlite_response.status_code == 200
    assert sqlite_response.json()["rowData"] == [{"symbol": "AAPL"}]
    assert duckdb_response.status_code == 200
    assert duckdb_response.json()["rowData"] == [{"symbol": "MSFT"}]


def test_ambiguous_db_source_requires_explicit_prefix(tmp_path):
    db_path = tmp_path / "ambiguous.db"
    db_path.write_text("", encoding="utf-8")
    conn = duckdb.connect(database=":memory:")

    with pytest.raises(ValueError, match="ambiguous source"):
        configure_connection(conn, [str(db_path)])

    conn.close()


def test_duplicate_attached_database_aliases_are_rejected(tmp_path):
    first = tmp_path / "one" / "warehouse.duckdb"
    second = tmp_path / "two" / "warehouse.duckdb"
    first.parent.mkdir()
    second.parent.mkdir()
    write_duckdb(first)
    write_duckdb(second)
    conn = duckdb.connect(database=":memory:")

    with pytest.raises(ValueError, match="duplicate source alias"):
        configure_connection(conn, [str(first), str(second)])

    conn.close()


def test_duplicate_attached_table_aliases_are_rejected(tmp_path):
    first = tmp_path / "one.duckdb"
    second = tmp_path / "two.duckdb"
    write_duckdb(first)
    write_duckdb(second)
    conn = duckdb.connect(database=":memory:")

    with pytest.raises(ValueError, match="duplicate table alias"):
        configure_connection(conn, [f"one={first}", f"two={second}"])

    conn.close()


def test_query_endpoint_rejects_mutating_sql(tmp_path):
    csv_path = tmp_path / "prices.csv"
    write_csv(csv_path)
    client = TestClient(create_app([f"prices={csv_path}"]))

    response = client.post("/query", json={"query": "CREATE TABLE x AS SELECT 1"})

    assert response.status_code == 400
    assert "read-only" in response.json()["detail"].lower()


def test_query_endpoint_applies_ssrm_filter_sort_and_window(tmp_path):
    csv_path = tmp_path / "prices.csv"
    write_csv(csv_path)
    client = TestClient(create_app([f"prices={csv_path}"]))

    response = client.post(
        "/query",
        json={
            "query": "SELECT symbol, price, sector FROM prices",
            "filterModel": {
                "sector": {
                    "filterType": "text",
                    "type": "equals",
                    "filter": "Technology",
                }
            },
            "sortModel": [{"colId": "price", "sort": "desc"}],
            "startRow": 1,
            "endRow": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["rowData"] == [
        {"symbol": "AAPL", "price": 150, "sector": "Technology"}
    ]
    assert response.json()["rowCount"] == 2
    assert response.json()["lastRow"] == 2


def test_create_app_accepts_custom_cors_origins(tmp_path):
    csv_path = tmp_path / "prices.csv"
    write_csv(csv_path)
    client = TestClient(
        create_app(
            [f"prices={csv_path}"],
            cors_origins=["https://workspace.example.com"],
        )
    )

    response = client.options(
        "/widgets.json",
        headers={
            "Origin": "https://workspace.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://workspace.example.com"
    )
