from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openbb_duck.discovery import (
    discover_tables,
    quote_identifier,
    schema_ref,
    table_schemas,
)
from openbb_duck.query import execute_ssrm_query


def default_query(data_dir: Path) -> str:
    refs = discover_tables(data_dir)
    if not refs:
        return "SELECT 1 AS value"

    namespace = schema_ref(data_dir)
    first_table = refs[0].name
    return (
        f"SELECT * FROM {quote_identifier(namespace.schema)}."
        f"{quote_identifier(first_table)} LIMIT 100"
    )


def widgets_json(data_dir: Path) -> dict:
    return {
        "duck_sql": {
            "name": "DuckDB SQL",
            "description": "Query local CSV, Parquet, and SQLite files with DuckDB.",
            "category": "Local Data",
            "type": "ssrm_advanced",
            "endpoint": "query",
            "schemaName": "ALL_DATABASES_ALL_SCHEMAS_ALL_TABLES",
            "params": [
                {
                    "paramName": "query",
                    "type": "text",
                    "description": "DuckDB SQL query over discovered local tables.",
                    "label": "SQL Query",
                    "show": False,
                    "language": "sql",
                    "value": default_query(data_dir),
                }
            ],
            "data": {"table": {"chartView": {"chartType": "column"}}},
            "gridData": {"w": 40, "h": 15, "minH": 10, "minW": 16},
        }
    }


def apps_json() -> list[dict]:
    return [
        {
            "name": "OpenBB Duck",
            "description": "Query local files with DuckDB.",
            "img": "",
            "img_dark": "",
            "img_light": "",
            "allowCustomization": True,
            "tabs": {
                "": {
                    "id": "",
                    "name": "",
                    "layout": [{"i": "duck_sql", "x": 0, "y": 0, "w": 40, "h": 15}],
                }
            },
            "groups": [],
            "prompts": [],
        }
    ]


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    resolved_data_dir = Path(data_dir or Path.cwd()).expanduser().resolve()
    app = FastAPI(
        title="OpenBB Duck",
        description="OpenBB Workspace backend for local DuckDB analytics.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://pro.openbb.co",
            "https://pro.openbb.dev",
            "http://localhost:1420",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": "OpenBB Duck", "data_dir": str(resolved_data_dir)}

    @app.get("/widgets.json")
    def get_widgets() -> dict:
        return widgets_json(resolved_data_dir)

    @app.get("/apps.json")
    def get_apps() -> list[dict]:
        return apps_json()

    @app.get("/table-schemas")
    def get_table_schemas() -> dict:
        return table_schemas(resolved_data_dir)

    @app.get("/semantic-views")
    def get_semantic_views() -> dict:
        return {}

    @app.post("/query")
    def query(body: dict = Body(default_factory=dict)) -> dict:
        return execute_ssrm_query(resolved_data_dir, body)

    return app
