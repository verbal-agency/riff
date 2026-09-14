"""Command-line entry points for local operation."""

from __future__ import annotations

import argparse
import logging

from .api import create_app
from .config import Settings
from .db import migrate
from .logging import configure_logging, event
from .worker import run_worker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riff")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="apply pending Postgres migrations")
    subparsers.add_parser("worker", help="run one scheduled worker cycle")
    api = subparsers.add_parser("api", help="start the HTTP API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc

    if args.command == "migrate":
        configure_logging(settings.log_level)
        applied = migrate(settings.database_url)
        event(logging.getLogger("riff.migrations"), "migrations.completed", applied=applied)
        return 0
    if args.command == "worker":
        run_worker(settings)
        return 0

    import uvicorn

    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0
