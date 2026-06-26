from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from openbb_duck.app import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7779


@dataclass(frozen=True)
class CliConfig:
    data_dir: Path
    host: str
    port: int
    reload: bool
    cors_origins: list[str] | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Serve an OpenBB Workspace backend over local DuckDB-readable files."
        ),
        epilog="Example: openbb-duck --data-dir ~/data --host 127.0.0.1 --port 7779",
    )
    parser.add_argument(
        "-d",
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "Folder containing CSV, Parquet, and SQLite files. Defaults to the "
            "current working directory. Env: OPENBB_DUCK_DATA_DIR."
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
            "Enable uvicorn reload mode for local development. "
            "Env: OPENBB_DUCK_RELOAD."
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
    env = environ or {}
    return CliConfig(
        data_dir=args.data_dir
        or _env_path(env, "OPENBB_DUCK_DATA_DIR")
        or Path.cwd(),
        host=args.host or env.get("OPENBB_DUCK_HOST") or DEFAULT_HOST,
        port=args.port or _env_int(env, "OPENBB_DUCK_PORT") or DEFAULT_PORT,
        reload=_coalesce_bool(
            args.reload,
            _env_bool(env, "OPENBB_DUCK_RELOAD"),
            default=False,
        ),
        cors_origins=args.cors_origins
        if args.cors_origins is not None
        else _env_csv(env, "OPENBB_DUCK_CORS_ORIGINS"),
    )


def _env_path(environ: Mapping[str, str], name: str) -> Path | None:
    value = environ.get(name)
    if not value:
        return None
    return Path(value)


def _env_int(environ: Mapping[str, str], name: str) -> int | None:
    value = environ.get(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_bool(environ: Mapping[str, str], name: str) -> bool | None:
    value = environ.get(name)
    if value is None or value == "":
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def _coalesce_bool(value: bool | None, fallback: bool | None, *, default: bool) -> bool:
    if value is not None:
        return value
    if fallback is not None:
        return fallback
    return default


def _env_csv(environ: Mapping[str, str], name: str) -> list[str] | None:
    value = environ.get(name)
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args, os.environ)
    except ValueError as exc:
        parser.error(str(exc))

    app = create_app(config.data_dir, cors_origins=config.cors_origins)
    uvicorn.run(app, host=config.host, port=config.port, reload=config.reload)
    return 0
