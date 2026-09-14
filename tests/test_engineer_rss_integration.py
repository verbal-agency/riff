import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from riff.cli import main
from riff.db import connection, migrate
from riff.engineer_rss import (
    EngineerRssSelectionError,
    load_selection_manifest,
    project_registries,
    selection_report,
    validate_selection_manifest,
)
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.ingestion import FeedResponse, PermanentFeedError
from riff.ingestion_repository import IngestionRepository, RunStatus
from riff.writing_ingestion import WritingIngestionRunner


ROOT = Path(__file__).parent
SELECTION_PATH = ROOT / "fixtures" / "engineer_sources" / "selection-manifest.json"
ENGINEER_PATH = ROOT.parent / "config" / "engineer_sources.json"
TECHNICAL_PATH = ROOT.parent / "config" / "technical_sources.json"
INGESTION_PATH = ROOT.parent / "config" / "ingestion_sources.json"
FEED_DIR = ROOT / "fixtures" / "engineer_sources"


def _selection_payload():
    return json.loads(SELECTION_PATH.read_text(encoding="utf-8"))


def _approved_selection():
    payload = _selection_payload()
    for selection in payload["selections"]:
        selection.update(
            permission_status="CONFIRMED",
            reviewed_at="2026-09-14",
            reviewed_by="operator",
            collection_decision="ENABLE",
            enabled=True,
        )
    return payload


def test_selection_manifest_requires_review_and_decision():
    selection = load_selection_manifest(SELECTION_PATH)
    report = selection_report(selection)
    assert len(selection["selections"]) == 3
    assert {item["status"] for item in report["selections"]} == {"pending"}

    approved = _approved_selection()
    validate_selection_manifest(approved)
    approved["selections"][0]["reviewed_by"] = None
    with pytest.raises(EngineerRssSelectionError, match="reviewed_by"):
        validate_selection_manifest(approved)


def test_projection_is_idempotent_and_preserves_identity():
    approved = _approved_selection()
    technical = json.loads(TECHNICAL_PATH.read_text(encoding="utf-8"))
    ingestion = json.loads(INGESTION_PATH.read_text(encoding="utf-8"))
    first_technical, first_ingestion = project_registries(approved, technical, ingestion)
    second_technical, second_ingestion = project_registries(approved, first_technical, first_ingestion)

    assert first_technical == second_technical
    assert first_ingestion == second_ingestion
    added = next(item for item in first_technical["sources"] if item["source_id"] == "writing-engineer-simon-willison")
    assert added["engineer_source_id"] == "engineer-simon-willison"
    assert added["correlation_group"] == "person:simon-willison"
    assert added["source_root"] == "https://simonwillison.net/"
    assert added["enabled"] is True


def test_pending_and_unsafe_selections_fail_closed():
    pending = _selection_payload()
    with pytest.raises(EngineerRssSelectionError, match="not eligible"):
        project_registries(
            pending,
            json.loads(TECHNICAL_PATH.read_text(encoding="utf-8")),
            json.loads(INGESTION_PATH.read_text(encoding="utf-8")),
        )

    unsafe = _selection_payload()
    unsafe["selections"][0]["endpoint"] = "https://user:password@example.com/feed"
    with pytest.raises(EngineerRssSelectionError, match="credential"):
        validate_selection_manifest(unsafe)


def test_cli_dry_run_and_validation_are_explicit(capsys):
    assert main(["source", "engineer-rss", "validate", "--manifest", str(SELECTION_PATH)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated == {"schema_version": 1, "selections": 3, "valid": True}

    assert main(["source", "engineer-rss", "preview", "--manifest", str(SELECTION_PATH)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["selections"][0]["status"] == "pending"


@pytest.fixture()
def repositories():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    return database_url, IngestionRepository(database_url), EvidenceRepository(database_url)


class FixtureFetcher:
    def __init__(self, filename):
        self.filename = filename
        self.calls = 0

    def fetch(self, endpoint):
        self.calls += 1
        return FeedResponse(
            body=(FEED_DIR / self.filename).read_bytes(),
            fetched_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            final_url=endpoint,
        )


@pytest.mark.postgres
def test_engineer_metadata_survives_rss_ingestion(repositories):
    database_url, ingestion, evidence = repositories
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "Simon engineer fixture", enabled=True)
    metadata = {
        "engineer_source_id": "engineer-simon-willison",
        "person_id": "simon-willison",
        "person_name": "Simon Willison",
        "source_ownership": "PERSONAL",
        "organization_at_publication": "Independent / Datasette",
        "source_root": "https://simonwillison.net/",
        "correlation_group": "person:simon-willison",
        "attribution_policy": "SOURCE_OWNED_PERSONAL",
    }
    configured = ingestion.configure_source(source.source_id, "https://example.com/simon.xml", metadata=metadata)
    summary = WritingIngestionRunner(ingestion, evidence, FixtureFetcher("rss-personal.xml")).run(source_ids=[source.source_id])
    assert (summary.status, summary.stored) == (RunStatus.SUCCEEDED, 2)
    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT metadata FROM retrievals r JOIN evidence_versions e ON e.evidence_id = r.evidence_id "
            "WHERE e.source_item_id IN (SELECT source_item_id FROM source_items WHERE source_id = %s)",
            (source.source_id,),
        ).fetchall()
    values = [row[0] for row in rows]
    assert {item["engineer_source_id"] for item in values} == {"engineer-simon-willison"}
    assert {item["attribution_disposition"] for item in values} == {"PERSONAL_MATCH", "CO_AUTHORED"}
    assert configured.metadata["person_id"] == "simon-willison"


@pytest.mark.postgres
def test_attribution_drift_is_permanent_and_does_not_guess(repositories):
    _, ingestion, evidence = repositories
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "Simon drift fixture", enabled=True)
    ingestion.configure_source(
        source.source_id,
        "https://example.com/drift.xml",
        metadata={"engineer_source_id": "engineer-simon-willison", "person_id": "simon-willison", "person_name": "Simon Willison", "source_ownership": "PERSONAL"},
    )
    summary = WritingIngestionRunner(ingestion, evidence, FixtureFetcher("rss-drift.xml")).run(source_ids=[source.source_id])
    assert summary.status == RunStatus.PARTIAL
    assert summary.failed_permanent == 1
    assert evidence.source_item_count(source.source_id) == 0
