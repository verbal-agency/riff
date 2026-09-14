"""Command-line entry points for local operation."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .api import create_app
from .capability_evaluation import evaluate_fixture
from .capabilities import CapabilityRepository, DeterministicNormalizer, NormalizationService
from .config import Settings
from .db import migrate
from .daily import load_fixture, run_fixture
from .evidence import SourceType
from .engineer_sources import load_manifest as load_engineer_source_manifest
from .engineer_rss import (
    EngineerRssSelectionError,
    load_selection_manifest,
    project_registries,
    selection_report,
    write_json,
)
from .evidence_repository import EvidenceRepository
from .github_ingestion import GitHubIngestionRunner, HttpGitHubFetcher
from .github_discovery import (
    DiscoveryPolicyError,
    FixtureDiscoveryFetcher,
    HttpGitHubDiscoveryFetcher,
    approve_candidates,
    discover,
    evaluate_fixture as evaluate_github_discovery_fixture,
    load_policy as load_github_discovery_policy,
    load_queue as load_github_discovery_queue,
    promote_candidates,
    write_queue as write_github_discovery_queue,
)
from .ingestion import HttpFeedFetcher
from .ingestion_repository import IngestionRepository, RunStatus
from .job_ingestion import JobIngestionRunner
from .logging import configure_logging, event
from .profile import ProfileRepository
from .profile_evaluation import evaluate_fixture as evaluate_profile_fixture
from .signal_evaluation import evaluate_fixture as evaluate_signal_fixture
from .source_manifest import load_manifest
from .riff_evaluation import evaluate_fixture as evaluate_riff_fixture
from .signals import SignalObservation, SignalRanker, SignalRepository
from .receipt_evaluation import evaluate_labeled_fixture
from .receipts import KeywordExtractor, ReceiptProcessor, ReceiptRepository
from .worker import run_worker
from .writing_ingestion import WritingIngestionRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riff")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="apply pending Postgres migrations")
    worker = subparsers.add_parser("worker", help="run one scheduled worker cycle")
    worker.add_argument("--fixture", help="run the deterministic daily pipeline fixture")
    worker.add_argument("--date", dest="run_date")
    worker.add_argument("--policy-version")
    worker.add_argument("--resume", action="store_true")
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
    source_validate = source_subparsers.add_parser("validate-manifest", help="validate the reviewed ingestion-source manifest")
    source_validate.add_argument("--manifest", default="config/ingestion_sources.json")
    source_validate_engineers = source_subparsers.add_parser("validate-engineer-manifest", help="validate the engineer-authored source manifest")
    source_validate_engineers.add_argument("--manifest", default="config/engineer_sources.json")
    source_engineer_rss = source_subparsers.add_parser("engineer-rss", help="review and project engineer-authored RSS selections")
    engineer_rss_subparsers = source_engineer_rss.add_subparsers(dest="engineer_rss_command", required=True)
    engineer_rss_validate = engineer_rss_subparsers.add_parser("validate", help="validate the engineer RSS selection manifest")
    engineer_rss_validate.add_argument("--manifest", default="config/engineer_rss_selections.json")
    engineer_rss_preview = engineer_rss_subparsers.add_parser("preview", help="show pending, blocked, and eligible selections")
    engineer_rss_preview.add_argument("--manifest", default="config/engineer_rss_selections.json")
    engineer_rss_project = engineer_rss_subparsers.add_parser("project", help="project enabled selections into both source registries")
    engineer_rss_project.add_argument("--manifest", default="config/engineer_rss_selections.json")
    engineer_rss_project.add_argument("--technical-registry", default="config/technical_sources.json")
    engineer_rss_project.add_argument("--ingestion-manifest", default="config/ingestion_sources.json")
    engineer_rss_project.add_argument("--selection-id", action="append")
    engineer_rss_project.add_argument("--apply", action="store_true", help="write the projected registries")
    github = subparsers.add_parser("github", help="evaluate bounded GitHub discovery")
    github_subparsers = github.add_subparsers(dest="github_command", required=True)
    github_discovery = github_subparsers.add_parser("evaluate-discovery", help="evaluate a recorded discovery benchmark")
    github_discovery.add_argument("--file", required=True)
    github_run = github_subparsers.add_parser("discover", help="run bounded topic/search discovery")
    github_run.add_argument("--policy", default="config/github_discovery.json")
    github_run.add_argument("--fixture", help="recorded search responses for an offline run")
    github_run.add_argument("--output", help="write the review queue to this JSON file")
    github_run.add_argument("--live", action="store_true", help="explicitly permit the bounded live GitHub API client")
    github_queue = github_subparsers.add_parser("queue", help="inspect a discovery review queue")
    github_queue.add_argument("--file", required=True)
    github_review = github_subparsers.add_parser("review", help="approve candidates in a review queue")
    github_review.add_argument("--file", required=True)
    github_review.add_argument("--candidate-id", action="append", required=True)
    github_review.add_argument("--apply", action="store_true", help="write the approved queue")
    github_promote = github_subparsers.add_parser("promote", help="promote approved candidates into the GitHub registry")
    github_promote.add_argument("--queue", required=True)
    github_promote.add_argument("--candidate-id", action="append", required=True)
    github_promote.add_argument("--registry", default="config/github_sources.json")
    github_promote.add_argument("--confirm", required=True, help="type PROMOTE to confirm the scoped write")
    github_promote.add_argument("--apply", action="store_true", help="write the registry and updated queue")
    ingest = subparsers.add_parser("ingest", help="collect configured sources once")
    ingest.add_argument("--source-id", action="append")
    ingest.add_argument("--source-type", choices=[item.value for item in SourceType])
    job = subparsers.add_parser("job", help="import permitted job-market data")
    job_subparsers = job.add_subparsers(dest="job_command", required=True)
    job_import = job_subparsers.add_parser("import", help="import a schema-versioned JSON fixture/export")
    job_import.add_argument("--source-id", required=True)
    job_import.add_argument("--file", required=True)
    job_import.add_argument("--content-limit", type=int, default=20_000)
    receipt = subparsers.add_parser("receipt", help="process and evaluate Evidence Receipts")
    receipt_subparsers = receipt.add_subparsers(dest="receipt_command", required=True)
    receipt_process = receipt_subparsers.add_parser("process", help="process pending evidence with the local extractor")
    receipt_process.add_argument("--evidence-id", action="append")
    receipt_process.add_argument("--limit", type=int, default=100)
    receipt_process.add_argument("--force", action="store_true")
    receipt_evaluate = receipt_subparsers.add_parser("evaluate", help="evaluate a labeled receipt fixture")
    receipt_evaluate.add_argument("--file", required=True)
    capability = subparsers.add_parser("capability", help="normalize and review capabilities")
    capability_subparsers = capability.add_subparsers(dest="capability_command", required=True)
    capability_normalize = capability_subparsers.add_parser("normalize", help="normalize successful receipts")
    capability_normalize.add_argument("--receipt-id", action="append")
    capability_normalize.add_argument("--limit", type=int, default=100)
    capability_normalize.add_argument("--force", action="store_true")
    capability_evaluate = capability_subparsers.add_parser("evaluate", help="evaluate a labeled normalization fixture")
    capability_evaluate.add_argument("--file", required=True)
    capability_inspect = capability_subparsers.add_parser("inspect", help="inspect a capability and its provenance")
    capability_inspect.add_argument("--capability-id", required=True)
    review = capability_subparsers.add_parser("review", help="record a reversible mapping decision")
    review_subparsers = review.add_subparsers(dest="review_action", required=True)
    for action in ("accept", "reject", "remap", "undo"):
        command = review_subparsers.add_parser(action)
        command.add_argument("--mapping-id", required=True)
        command.add_argument("--actor", default="operator")
        command.add_argument("--reason", required=True)
        if action == "remap":
            command.add_argument("--entity-id", required=True)
    split = review_subparsers.add_parser("split")
    split.add_argument("--mapping-id", required=True)
    split.add_argument("--name", action="append", required=True)
    split.add_argument("--actor", default="operator")
    split.add_argument("--reason", required=True)
    profile = subparsers.add_parser("profile", help="manage the user capability profile")
    profile_subparsers = profile.add_subparsers(dest="profile_command", required=True)
    profile_import = profile_subparsers.add_parser("import-public", help="import a bounded public profile fixture")
    profile_import.add_argument("--file", required=True)
    profile_import.add_argument("--limit", type=int, default=100)
    profile_assess = profile_subparsers.add_parser("assess", help="recompute a capability gap assessment")
    profile_assess.add_argument("--capability-id", required=True)
    profile_view = profile_subparsers.add_parser("view", help="view one capability profile slice")
    profile_view.add_argument("--capability-id", required=True)
    profile_view.add_argument("--public", action="store_true")
    profile_view.add_argument("--limit", type=int, default=100)
    profile_evaluate = profile_subparsers.add_parser("evaluate", help="evaluate gap-classification fixtures")
    profile_evaluate.add_argument("--file", required=True)
    ledger = profile_subparsers.add_parser("ledger", help="manage private Experience Ledger entries")
    ledger_subparsers = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_add = ledger_subparsers.add_parser("add")
    ledger_add.add_argument("--capability-id", required=True)
    ledger_add.add_argument("--entry", required=True)
    ledger_add.add_argument("--employer-or-context")
    ledger_list = ledger_subparsers.add_parser("list")
    ledger_list.add_argument("--limit", type=int, default=100)
    ledger_update = ledger_subparsers.add_parser("update")
    ledger_update.add_argument("--ledger-id", required=True)
    ledger_update.add_argument("--entry", required=True)
    ledger_update.add_argument("--employer-or-context")
    ledger_archive = ledger_subparsers.add_parser("archive")
    ledger_archive.add_argument("--ledger-id", required=True)
    signal = subparsers.add_parser("signal", help="generate and inspect ranked candidate signals")
    signal_subparsers = signal.add_subparsers(dest="signal_command", required=True)
    signal_evaluate = signal_subparsers.add_parser("evaluate", help="evaluate adversarial ranking fixtures")
    signal_evaluate.add_argument("--file", required=True)
    signal_rank = signal_subparsers.add_parser("rank", help="rank observations from a bounded JSON fixture")
    signal_rank.add_argument("--file", required=True)
    riff = subparsers.add_parser("riff", help="evaluate daily Riff generation fixtures")
    riff_subparsers = riff.add_subparsers(dest="riff_command", required=True)
    riff_evaluate = riff_subparsers.add_parser("evaluate", help="evaluate a golden Riff fixture")
    riff_evaluate.add_argument("--file", required=True)
    daily = subparsers.add_parser("daily", help="run a local daily Riff smoke fixture")
    daily_subparsers = daily.add_subparsers(dest="daily_command", required=True)
    daily_generate = daily_subparsers.add_parser("generate", help="generate and persist a daily Riff result")
    daily_generate.add_argument("--file", required=True)
    daily_generate.add_argument("--date", dest="run_date")
    daily_generate.add_argument("--policy-version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "receipt" and args.receipt_command == "evaluate":
        print(json.dumps(evaluate_labeled_fixture(args.file), sort_keys=True))
        return 0
    if args.command == "capability" and args.capability_command == "evaluate":
        print(json.dumps(evaluate_fixture(args.file), sort_keys=True))
        return 0
    if args.command == "profile" and args.profile_command == "evaluate":
        print(json.dumps(evaluate_profile_fixture(args.file), sort_keys=True))
        return 0
    if args.command == "signal" and args.signal_command == "evaluate":
        print(json.dumps(evaluate_signal_fixture(args.file), sort_keys=True))
        return 0
    if args.command == "riff" and args.riff_command == "evaluate":
        print(json.dumps(evaluate_riff_fixture(args.file), sort_keys=True))
        return 0
    if args.command == "github" and args.github_command == "evaluate-discovery":
        try:
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            print(json.dumps(evaluate_github_discovery_fixture(payload), sort_keys=True))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"GitHub discovery fixture error: {exc}") from exc
        return 0
    if args.command == "github" and args.github_command in {"discover", "queue", "review", "promote"}:
        try:
            if args.github_command == "discover":
                policy = load_github_discovery_policy(args.policy)
                if args.fixture:
                    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
                    result = discover(policy, FixtureDiscoveryFetcher(fixture), fixture_id=str(fixture.get("fixture_id", args.fixture)))
                else:
                    if not args.live:
                        raise DiscoveryPolicyError("live discovery requires --live; use --fixture for offline runs")
                    if not policy.enabled:
                        raise DiscoveryPolicyError("discovery policy is disabled")
                    result = discover(policy, HttpGitHubDiscoveryFetcher(token=os.environ.get("GITHUB_TOKEN")))
                if args.output:
                    write_github_discovery_queue(args.output, result)
                print(json.dumps(result, sort_keys=True))
                return 0
            if args.github_command == "queue":
                print(json.dumps(load_github_discovery_queue(args.file), sort_keys=True))
                return 0
            if args.github_command == "review":
                queue = load_github_discovery_queue(args.file)
                result = approve_candidates(queue, args.candidate_id)
                if args.apply:
                    write_github_discovery_queue(args.file, result)
                print(json.dumps(result, sort_keys=True))
                return 0
            queue = load_github_discovery_queue(args.queue)
            registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
            result = promote_candidates(queue, args.candidate_id, confirmation=args.confirm, config=registry, apply=args.apply)
            if args.apply:
                write_github_discovery_queue(args.queue, result["queue"])
                Path(args.registry).write_text(json.dumps(result["config"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, sort_keys=True))
            return 0
        except (OSError, ValueError, DiscoveryPolicyError) as exc:
            raise SystemExit(f"GitHub discovery error: {exc}") from exc
    if args.command == "source" and args.source_command == "validate-manifest":
        try:
            manifest = load_manifest(args.manifest)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"source manifest error: {exc}") from exc
        result = {"schema_version": manifest["schema_version"], "sources": len(manifest["sources"]), "valid": True}
        if isinstance(manifest.get("rss_inventory"), list):
            result["rss_inventory"] = len(manifest["rss_inventory"])
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "source" and args.source_command == "validate-engineer-manifest":
        try:
            manifest = load_engineer_source_manifest(args.manifest)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"engineer source manifest error: {exc}") from exc
        print(json.dumps({"schema_version": manifest["schema_version"], "sources": len(manifest["sources"]), "valid": True}, sort_keys=True))
        return 0
    if args.command == "source" and args.source_command == "engineer-rss":
        try:
            selection = load_selection_manifest(args.manifest)
            if args.engineer_rss_command == "validate":
                print(json.dumps({"schema_version": selection["schema_version"], "selections": len(selection["selections"]), "valid": True}, sort_keys=True))
                return 0
            if args.engineer_rss_command == "preview":
                print(json.dumps(selection_report(selection), sort_keys=True))
                return 0
            technical = json.loads(Path(args.technical_registry).read_text(encoding="utf-8"))
            ingestion_manifest = json.loads(Path(args.ingestion_manifest).read_text(encoding="utf-8"))
            projected_technical, projected_ingestion = project_registries(
                selection,
                technical,
                ingestion_manifest,
                selection_ids=args.selection_id,
            )
            if args.apply:
                write_json(args.technical_registry, projected_technical)
                write_json(args.ingestion_manifest, projected_ingestion)
                result = {"status": "applied", "technical_sources": len(projected_technical["sources"]), "ingestion_sources": len(projected_ingestion["sources"])}
            else:
                result = {"status": "dry_run", "technical_sources": len(projected_technical["sources"]), "ingestion_sources": len(projected_ingestion["sources"])}
            print(json.dumps(result, sort_keys=True))
            return 0
        except (OSError, ValueError, EngineerRssSelectionError) as exc:
            raise SystemExit(f"engineer RSS selection error: {exc}") from exc
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc

    if args.command == "migrate":
        configure_logging(settings.log_level)
        applied = migrate(settings.database_url)
        event(logging.getLogger("riff.migrations"), "migrations.completed", applied=applied)
        return 0
    if args.command == "daily" and args.daily_command == "generate":
        from datetime import date

        try:
            requested_date = date.fromisoformat(args.run_date) if args.run_date else None
            fixture = load_fixture(args.file, run_date=requested_date, policy_version=args.policy_version)
            print(json.dumps(run_fixture(settings.database_url, fixture), sort_keys=True))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"daily fixture error: {exc}") from exc
        return 0
    if args.command == "worker":
        from datetime import date

        run_worker(settings, fixture_path=args.fixture, run_date=date.fromisoformat(args.run_date) if args.run_date else None, policy_version=args.policy_version, resume=args.resume)
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
                    canonical_root=(
                        entry.get("source_root")
                        if str(entry.get("source_root", "")).lower().startswith(("http://", "https://"))
                        else None
                    ),
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
                        metadata={
                            key: entry[key]
                            for key in (
                                "engineer_source_id", "person_id", "person_name", "source_ownership",
                                "organization_at_publication", "source_root", "correlation_group",
                                "attribution_policy", "syndication_root", "discovery_run_id",
                                "discovered_by", "provider_repository_id",
                            )
                            if key in entry
                        },
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
    if args.command == "job":
        if args.job_command != "import":
            raise SystemExit(f"unsupported job command: {args.job_command}")
        summary = JobIngestionRunner(
            IngestionRepository(settings.database_url),
            EvidenceRepository(settings.database_url),
            content_limit=args.content_limit,
        ).run_file(args.file, source_ids=[args.source_id])
        print(json.dumps(asdict(summary), sort_keys=True, default=str))
        return 0 if summary.status != RunStatus.FAILED else 1
    if args.command == "receipt":
        if args.limit < 1 or args.limit > 500:
            raise SystemExit("--limit must be between 1 and 500")
        evidence = EvidenceRepository(settings.database_url)
        evidence_ids = (args.evidence_id[: args.limit] if args.evidence_id else evidence.list_evidence_ids(limit=args.limit))
        summary = ReceiptProcessor(
            evidence,
            ReceiptRepository(settings.database_url),
            KeywordExtractor(),
        ).process(evidence_ids, force=args.force)
        print(json.dumps(asdict(summary), sort_keys=True, default=str))
        return 0 if not (summary.failed_validation or summary.failed_transient) else 1
    if args.command == "capability":
        repository = CapabilityRepository(settings.database_url)
        if args.capability_command == "normalize":
            if not 1 <= args.limit <= 500:
                raise SystemExit("--limit must be between 1 and 500")
            summary = NormalizationService(
                ReceiptRepository(settings.database_url), repository, DeterministicNormalizer()
            ).normalize(args.receipt_id, limit=args.limit, force=args.force)
            print(json.dumps(asdict(summary), sort_keys=True, default=str))
            return 0
        if args.capability_command == "inspect":
            inspection = repository.inspect_capability(args.capability_id)
            if inspection is None:
                raise SystemExit("capability not found")
            print(json.dumps(asdict(inspection), sort_keys=True, default=str))
            return 0
        if args.capability_command == "review":
            if args.review_action == "split":
                result = repository.split(args.mapping_id, args.name, actor=args.actor, reason=args.reason)
            else:
                result = repository.review(
                    args.mapping_id,
                    args.review_action.upper(),
                    actor=args.actor,
                    reason=args.reason,
                    entity_id=getattr(args, "entity_id", None),
                )
            print(json.dumps(asdict(result), sort_keys=True, default=str))
            return 0
    if args.command == "profile":
        repository = ProfileRepository(settings.database_url)
        if args.profile_command == "import-public":
            result = repository.import_public_fixture(args.file, limit=args.limit)
        elif args.profile_command == "assess":
            result = repository.assess(args.capability_id)
        elif args.profile_command == "view":
            result = repository.view(args.capability_id, public=args.public, limit=args.limit)
        elif args.profile_command == "ledger" and args.ledger_command == "add":
            result = repository.create_ledger_entry(args.capability_id, args.entry, employer_or_context=args.employer_or_context)
        elif args.profile_command == "ledger" and args.ledger_command == "list":
            result = repository.list_ledger_entries(limit=args.limit)
        elif args.profile_command == "ledger" and args.ledger_command == "update":
            result = repository.update_ledger_entry(args.ledger_id, args.entry, employer_or_context=args.employer_or_context)
        elif args.profile_command == "ledger" and args.ledger_command == "archive":
            result = repository.archive_ledger_entry(args.ledger_id)
        else:
            raise SystemExit(f"unsupported profile command: {args.profile_command}")
        print(json.dumps(asdict(result), sort_keys=True, default=str))
        return 0
    if args.command == "signal" and args.signal_command == "rank":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or not isinstance(payload.get("observations"), list):
            raise SystemExit("signal fixture requires schema_version 1 and observations")
        observations = [SignalObservation(observed_at=datetime.fromisoformat(item["observed_at"]), **{key: item[key] for key in item if key != "observed_at"}) for item in payload["observations"]]
        result = SignalRanker(SignalRepository(settings.database_url)).rank(observations, window_start=datetime.fromisoformat(payload["window_start"]), window_end=datetime.fromisoformat(payload["window_end"]))
        print(json.dumps(asdict(result), sort_keys=True, default=str))
        return 0

    import uvicorn

    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0
