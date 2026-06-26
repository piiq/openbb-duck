from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from openbb_duck.app import create_app


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
        default=Path.cwd(),
        help=(
            "Folder containing CSV, Parquet, and SQLite files. Defaults to the "
            "current working directory."
        ),
    )
    parser.add_argument(
        "-H",
        "--host",
        default="127.0.0.1",
        help="Host interface to bind. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=7779,
        help="Port to bind. Defaults to 7779.",
    )
    parser.add_argument(
        "-r",
        "--reload",
        action="store_true",
        help="Enable uvicorn reload mode for local development.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = create_app(args.data_dir)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0
