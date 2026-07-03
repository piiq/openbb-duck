from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass

import uvicorn

from openbb_duck.app import create_app
from openbb_duck.discovery import source_specs


@dataclass(frozen=True)
class CliConfig:
    sources: list[str]
    host: str
    port: int
    reload: bool
    cors_origins: list[str] | None


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser with examples for humans and agent users."""
    parser = argparse.ArgumentParser(
        description=("Serve an OpenBB Workspace backend for DuckDB sources."),
        epilog=(
            "Examples:\n"
            "  openbb-duck --source './exports/*.parquet'\n"
            "  openbb-duck --source './exports/**/*.csv'\n"
            "  openbb-duck --source prices=./prices.parquet\n"
            "  openbb-duck --source duck=duckdb:./warehouse.db\n"
            "  openbb-duck --source warehouse=./warehouse.duckdb\n"
            "  openbb-duck --source portfolio=sqlite:./portfolio.db\n"
            "  openbb-duck --source lake=ducklake:metadata.ducklake\n"
            "  openbb-duck --source 's3://bucket/path/**/*.parquet'\n\n"
            "Rules:\n"
            "  --source is required and may be repeated. Globs are supported.\n"
            "  Use alias=source for stable SQL names.\n"
            "  The .db extension is ambiguous."
            " Use duckdb:./file.db or sqlite:./file.db.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--source",
        dest="sources",
        action="append",
        help=(
            "Explicit source file, glob, attached database, or DuckLake URI. "
            "May be repeated. Env: OPENBB_DUCK_SOURCES, comma-separated."
        ),
    )
    parser.add_argument(
        "-H",
        "--host",
        default=None,
        help="Host interface to bind. Defaults to 127.0.0.1. Env: OPENBB_DUCK_HOST.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        help="Port to bind. Defaults to 7779. Env: OPENBB_DUCK_PORT.",
    )
    parser.add_argument(
        "-r",
        "--reload",
        dest="reload",
        action="store_true",
        default=None,
        help=(
            "Enable uvicorn reload mode for local development. Env: OPENBB_DUCK_RELOAD."
        ),
    )
    parser.add_argument(
        "--no-reload",
        dest="reload",
        action="store_false",
        help="Disable uvicorn reload mode, overriding OPENBB_DUCK_RELOAD.",
    )
    parser.add_argument(
        "-c",
        "--cors-origin",
        dest="cors_origins",
        action="append",
        help=(
            "Allowed CORS origin. May be passed multiple times. Defaults to "
            "OpenBB Workspace origins. Env: OPENBB_DUCK_CORS_ORIGINS, "
            "comma-separated."
        ),
    )
    return parser


def resolve_config(
    args: argparse.Namespace,
    environ: Mapping[str, str] | None = None,
) -> CliConfig:
    """Resolve CLI/env/default precedence and enforce required sources."""
    env = environ or {}
    sources = (
        args.sources
        if args.sources is not None
        else _env_csv(env, "OPENBB_DUCK_SOURCES")
    )
    if not sources:
        raise ValueError("at least one --source is required")
    source_specs(sources)
    return CliConfig(
        sources=sources,
        host=args.host or env.get("OPENBB_DUCK_HOST") or "127.0.0.1",
        port=args.port or _env_int(env, "OPENBB_DUCK_PORT") or 7779,
        reload=args.reload
        if args.reload is not None
        else (_env_bool(env, "OPENBB_DUCK_RELOAD") or False),
        cors_origins=args.cors_origins
        if args.cors_origins is not None
        else _env_csv(env, "OPENBB_DUCK_CORS_ORIGINS"),
    )


def _env_int(environ: Mapping[str, str], name: str) -> int | None:
    """Parse optional integer env vars so argparse owns CLI parsing only."""
    value = environ.get(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_bool(environ: Mapping[str, str], name: str) -> bool | None:
    """Parse boolean env values for reload without accepting vague strings."""
    value = environ.get(name)
    if value is None or value == "":
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def _env_csv(environ: Mapping[str, str], name: str) -> list[str] | None:
    """Parse repeated options from env without adding another dependency."""
    value = environ.get(name)
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    """Parse config, build the ASGI app, and hand it to uvicorn."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args, os.environ)
    except ValueError as exc:
        parser.error(str(exc))

    app = create_app(config.sources, cors_origins=config.cors_origins)
    uvicorn.run(app, host=config.host, port=config.port, reload=config.reload)
    return 0
