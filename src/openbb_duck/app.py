from __future__ import annotations

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openbb_duck.discovery import (
    quote_identifier,
    table_schemas,
)
from openbb_duck.query import execute_ssrm_query

DEFAULT_CORS_ORIGINS = (
    "https://pro.openbb.co",
    "https://pro.openbb.dev",
    "http://localhost:1420",
)


ALL_SCHEMAS_NAME = "ALL_DATABASES_ALL_SCHEMAS_ALL_TABLES"


def queryable_schemas(schemas: dict) -> list[tuple[str, dict]]:
    """Return one autocomplete entry per non-system table, preferring short names."""
    entries: dict[tuple[str, str, str], tuple[str, dict]] = {}
    for name, schema in schemas.items():
        if schema["schema"] == "information_schema":
            continue
        if schema["database"] == schema["tableName"] and schema["schema"] == "":
            key = ("memory", "main", schema["tableName"])
        else:
            key = (schema["database"], schema["schema"], schema["tableName"])
        if key not in entries or "." not in name:
            entries[key] = (name, schema)
    return list(entries.values())


def default_query_from_schemas(schemas: dict) -> str:
    """Build the widget's initial query from registered non-system sources."""
    for _, schema in queryable_schemas(schemas):
        if (
            schema["database"] == "memory"
            and schema["schema"] == "main"
            or schema["schema"] == ""
        ):
            return f"SELECT * FROM {quote_identifier(schema['tableName'])} LIMIT 100"
        return (
            f"SELECT * FROM {quote_identifier(schema['database'])}."
            f"{quote_identifier(schema['schema'])}."
            f"{quote_identifier(schema['tableName'])} LIMIT 100"
        )
    raise ValueError("at least one queryable --source is required")


def widget_schema_name(schemas: dict) -> str:
    """Use exact table schema for one table so SQL column autocomplete works."""
    queryable = queryable_schemas(schemas)
    if len(queryable) == 1:
        return queryable[0][0]
    return ALL_SCHEMAS_NAME


def widgets_json(sources: list[str]) -> dict:
    """Return the single SQL widget Terminal Pro loads from /widgets.json."""
    schemas = table_schemas(sources)
    return {
        "duck_sql": {
            "name": "DuckDB SQL",
            "description": "Query local CSV, Parquet, and SQLite files with DuckDB.",
            "category": "Local Data",
            "type": "ssrm_advanced",
            "endpoint": "query",
            "schemaName": widget_schema_name(schemas),
            "params": [
                {
                    "paramName": "query",
                    "type": "text",
                    "description": "DuckDB SQL query over discovered local tables.",
                    "label": "SQL Query",
                    "show": False,
                    "language": "sql",
                    "value": default_query_from_schemas(schemas),
                }
            ],
            "data": {"table": {"chartView": {"chartType": "column"}}},
            "gridData": {"w": 40, "h": 15, "minH": 10, "minW": 16},
        }
    }


def create_app(
    sources: list[str],
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="OpenBB Duck",
        description="OpenBB Workspace backend for local DuckDB analytics.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            DEFAULT_CORS_ORIGINS if cors_origins is None else cors_origins
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, list[str] | str]:
        return {"name": "OpenBB Duck", "sources": sources}

    @app.get("/widgets.json")
    def get_widgets() -> dict:
        return widgets_json(sources)

    @app.get("/apps.json")
    def get_apps() -> list[dict]:
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
                        "layout": [
                            {"i": "duck_sql", "x": 0, "y": 0, "w": 40, "h": 15}
                        ],
                    }
                },
                "groups": [],
                "prompts": [],
            }
        ]

    @app.get("/table-schemas")
    def get_table_schemas() -> dict:
        return table_schemas(sources)

    @app.get("/semantic-views")
    def get_semantic_views() -> dict:
        return {}

    @app.post("/query")
    def query(body: dict = Body(default_factory=dict)) -> dict:
        return execute_ssrm_query(sources, body)

    return app
