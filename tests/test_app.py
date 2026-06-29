import sqlite3

from fastapi.testclient import TestClient

from openbb_duck.app import create_app


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


def test_widgets_expose_ssrm_advanced_sql_widget(tmp_path):
    write_csv(tmp_path / "prices.csv")
    client = TestClient(create_app(tmp_path))

    response = client.get("/widgets.json")

    assert response.status_code == 200
    widgets = response.json()
    assert list(widgets) == ["duck_sql"]
    assert widgets["duck_sql"]["type"] == "ssrm_advanced"
    assert widgets["duck_sql"]["schemaName"] == "ALL_DATABASES_ALL_SCHEMAS_ALL_TABLES"
    assert widgets["duck_sql"]["params"][0]["language"] == "sql"
    assert (
        widgets["duck_sql"]["params"][0]["value"]
        == f'SELECT * FROM "{tmp_path.name}"."prices" LIMIT 100'
    )


def test_table_schemas_include_csv_and_sqlite_tables(tmp_path):
    write_csv(tmp_path / "prices.csv")
    write_sqlite(tmp_path / "portfolio.sqlite")
    client = TestClient(create_app(tmp_path))

    response = client.get("/table-schemas")

    assert response.status_code == 200
    schemas = response.json()
    prices_schema_name = f"memory.{tmp_path.name}.prices"
    positions_schema_name = f"memory.{tmp_path.name}.portfolio_positions"
    assert prices_schema_name in schemas
    assert positions_schema_name in schemas
    assert "prices" in schemas
    assert schemas["prices"]["database"] == "prices"
    assert schemas["prices"]["schema"] == ""
    assert schemas["prices"]["tableName"] == "prices"
    assert "portfolio_positions" in schemas
    assert schemas[prices_schema_name]["database"] == "memory"
    assert schemas[prices_schema_name]["schema"] == tmp_path.name
    assert schemas[prices_schema_name]["tableName"] == "prices"
    assert [column["name"] for column in schemas[prices_schema_name]["columns"]] == [
        "symbol",
        "price",
        "sector",
    ]
    assert [column["name"] for column in schemas[positions_schema_name]["columns"]] == [
        "symbol",
        "quantity",
    ]


def test_table_schemas_include_duckdb_information_schema(tmp_path):
    write_csv(tmp_path / "prices.csv")
    client = TestClient(create_app(tmp_path))

    response = client.get("/table-schemas")

    assert response.status_code == 200
    schemas = response.json()
    assert "information_schema.columns" in schemas
    assert "information_schema.tables" in schemas
    assert "information_schema.schemata" in schemas
    columns_schema = schemas["information_schema.columns"]
    assert columns_schema["database"] == "memory"
    assert columns_schema["schema"] == "information_schema"
    assert columns_schema["tableName"] == "columns"
    assert columns_schema["kind"] == "VIEW"
    assert {"column_name", "table_name", "table_schema"}.issubset(
        {column["name"] for column in columns_schema["columns"]}
    )


def test_query_endpoint_accepts_schema_qualified_file_views(tmp_path):
    write_csv(tmp_path / "prices.csv")
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/query",
        json={
            "query": f'SELECT symbol FROM "{tmp_path.name}"."prices" ORDER BY symbol',
            "startRow": 0,
            "endRow": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["rowData"] == [
        {"symbol": "AAPL"},
        {"symbol": "JPM"},
        {"symbol": "MSFT"},
    ]


def test_query_endpoint_returns_ssrm_rows_with_sort_and_pagination(tmp_path):
    write_csv(tmp_path / "prices.csv")
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/query",
        json={
            "query": 'SELECT symbol, price FROM "prices"',
            "startRow": 0,
            "endRow": 2,
            "sortModel": [{"colId": "price", "sort": "desc"}],
            "filterModel": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rowCount"] == 3
    assert payload["rowData"] == [
        {"symbol": "MSFT", "price": 350},
        {"symbol": "JPM", "price": 195},
    ]


def test_query_endpoint_rejects_mutating_sql(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.post("/query", json={"query": "CREATE TABLE x AS SELECT 1"})

    assert response.status_code == 400
    assert "read-only" in response.json()["detail"].lower()


def test_create_app_accepts_custom_cors_origins(tmp_path):
    client = TestClient(
        create_app(tmp_path, cors_origins=["https://workspace.example.com"])
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
