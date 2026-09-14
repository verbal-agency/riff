"""Command-line entry points for local operation."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from .api import create_app
from .config import Settings
from .db import migrate
from .evidence import SourceType
from .evidence_repository import EvidenceRepository
from .github_ingestion import GitHubIngestionRunner, HttpGitHubFetcher
from .ingestion import HttpFeedFetcher
from .ingestion_repository import IngestionRepository, RunStatus
from .logging import configure_logging, event
from .worker import run_worker
from .writing_ingestion import WritingIngestionRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riff")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="apply pending Postgres migrations")
    subparsers.add_parser("worker", help="run one scheduled worker cycle")
    api = subparsers.add_parser("api", help="start the HTTP API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    source = subparsers.add_parser("source", help="manage curated source configuration")
    source_subparsers = source.add_subparsers(dest="source_command", required=True)
    source_add = source_subparsers.add_parser("add", help="add or update a feed source")
    source_add.add_argument("--name", required=True)
    source_add.add_argument("--endpoint", required=True)
    source_add.add_argument("--source-type", choices=[item.value for item in SourceType], default=SourceType.TECHNICAL_WRITING.value)
    source_add.add_argument("--source-id")
    source_add.add_argument("--disabled", action="store_true")
    source_sync = source_subparsers.add_parser("sync", help="sync a JSON source registry")
    source_sync.add_argument("--registry", default="config/technical_sources.json")
    source_toggle = source_subparsers.add_parser("enable", help="enable a configured source")
    source_toggle.add_argument("--source-id", required=True)
    source_toggle = source_subparsers.add_parser("disable", help="disable a configured source")
    source_toggle.add_argument("--source-id", required=True)
    ingest = subparsers.add_parser("ingest", help="collect configured sources once")
    ingest.add_argument("--source-id", action="append")
    ingest.add_argument("--source-type", choices=[item.value for item in SourceType])
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
    if args.command == "source":
        ingestion = IngestionRepository(settings.database_url)
        evidence = EvidenceRepository(settings.database_url)
        if args.source_command == "add":
            source = evidence.create_source(
                SourceType(args.source_type),
                args.name,
                enabled=not args.disabled,
                source_id=args.source_id,
            )
            configured = ingestion.configure_source(
                source.source_id,
                args.endpoint,
                enabled=source.enabled,
                cursor_kind="github:releases" if source.source_type == SourceType.GITHUB else "updated_at",
            )
            print(json.dumps({"source_id": configured.source_id, "name": configured.name, "enabled": configured.enabled}, sort_keys=True))
            return 0
        if args.source_command == "sync":
            registry_path = Path(args.registry)
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if registry.get("schema_version") != 1 or not isinstance(registry.get("sources"), list):
                raise SystemExit("source registry must contain schema_version 1 and a sources list")
            synced = []
            for entry in registry["sources"]:
                source = evidence.create_source(
                    SourceType(entry["source_type"]),
                    entry["name"],
                    enabled=bool(entry.get("enabled", True)),
                    source_id=entry.get("source_id"),
                )
                synced.append(
                    ingestion.configure_source(
                        source.source_id,
                        entry["endpoint"],
                        enabled=source.enabled,
                        config_version=int(entry.get("config_version", 1)),
                        cursor_kind=entry.get(
                            "cursor_kind",
                            "github:releases" if source.source_type == SourceType.GITHUB else "updated_at",
                        ),
                    )
                )
            print(json.dumps({"synced": len(synced)}, sort_keys=True))
            return 0
        ingestion.set_source_enabled(args.source_id, args.source_command == "enable")
        print(json.dumps({"source_id": args.source_id, "enabled": args.source_command == "enable"}, sort_keys=True))
        return 0
    if args.command == "ingest":
        ingestion = IngestionRepository(settings.database_url)
        evidence = EvidenceRepository(settings.database_url)
        source_type = SourceType(args.source_type) if args.source_type else None
        if source_type == SourceType.GITHUB:
            summary = GitHubIngestionRunner(
                ingestion,
                evidence,
                HttpGitHubFetcher(token=os.environ.get("GITHUB_TOKEN")),
            ).run(source_ids=args.source_id, source_type=source_type)
        else:
            summary = WritingIngestionRunner(ingestion, evidence, HttpFeedFetcher()).run(
                source_ids=args.source_id,
                source_type=source_type,
            )
        print(json.dumps(asdict(summary), sort_keys=True, default=str))
        return 0 if summary.status != RunStatus.FAILED else 1

    import uvicorn

    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0
