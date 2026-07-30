from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass

import uvicorn

from openbb_duck.app import create_app
from openbb_duck.discovery import ObjectStorageConfig, source_specs


@dataclass(frozen=True)
class CliConfig:
    sources: list[str]
    host: str
    port: int
    reload: bool
    cors_origins: list[str] | None
    api_token: str | None
    quack_token: str | None
    object_storage: ObjectStorageConfig | None


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
            "  openbb-duck --source remote=quack:localhost\n"
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
    parser.add_argument(
        "-q",
        "--quack-token",
        default=None,
        help="Token for Quack remote sources. Env: OPENBB_DUCK_QUACK_TOKEN.",
    )
    parser.add_argument(
        "--s3-endpoint",
        default=None,
        help="S3-compatible endpoint. Env: OPENBB_DUCK_S3_ENDPOINT.",
    )
    parser.add_argument(
        "--s3-access-key-id",
        default=None,
        help="S3-compatible access key ID. Env: OPENBB_DUCK_S3_ACCESS_KEY_ID.",
    )
    parser.add_argument(
        "--s3-secret-access-key",
        default=None,
        help=(
            "S3-compatible secret access key. "
            "Env: OPENBB_DUCK_S3_SECRET_ACCESS_KEY."
        ),
    )
    parser.add_argument(
        "--s3-region",
        default=None,
        help="S3-compatible region. Defaults to auto. Env: OPENBB_DUCK_S3_REGION.",
    )
    parser.add_argument(
        "--s3-url-style",
        default=None,
        choices=("path", "vhost"),
        help=(
            "S3-compatible URL style. Defaults to path. "
            "Env: OPENBB_DUCK_S3_URL_STYLE."
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
        api_token=env.get("OPENBB_DUCK_API_TOKEN") or None,
        quack_token=args.quack_token or env.get("OPENBB_DUCK_QUACK_TOKEN") or None,
        object_storage=_object_storage_config(args, env),
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


def _object_storage_config(
    args: argparse.Namespace,
    environ: Mapping[str, str],
) -> ObjectStorageConfig | None:
    endpoint = args.s3_endpoint or environ.get("OPENBB_DUCK_S3_ENDPOINT")
    access_key_id = args.s3_access_key_id or environ.get(
        "OPENBB_DUCK_S3_ACCESS_KEY_ID"
    )
    secret_access_key = args.s3_secret_access_key or environ.get(
        "OPENBB_DUCK_S3_SECRET_ACCESS_KEY"
    )
    if not endpoint and not access_key_id and not secret_access_key:
        return None
    if not endpoint or not access_key_id or not secret_access_key:
        raise ValueError(
            "OPENBB_DUCK_S3_ENDPOINT, OPENBB_DUCK_S3_ACCESS_KEY_ID, and "
            "OPENBB_DUCK_S3_SECRET_ACCESS_KEY must be set together"
        )
    return ObjectStorageConfig(
        endpoint=endpoint,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=args.s3_region or environ.get("OPENBB_DUCK_S3_REGION", "auto"),
        url_style=args.s3_url_style or environ.get("OPENBB_DUCK_S3_URL_STYLE", "path"),
    )


def main(argv: list[str] | None = None) -> int:
    """Parse config, build the ASGI app, and hand it to uvicorn."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args, os.environ)
    except ValueError as exc:
        parser.error(str(exc))

    app = create_app(
        config.sources,
        cors_origins=config.cors_origins,
        api_token=config.api_token,
        quack_token=config.quack_token,
        object_storage=config.object_storage,
    )
    uvicorn.run(app, host=config.host, port=config.port, reload=config.reload)
    return 0
