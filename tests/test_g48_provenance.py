import os
import uuid
from datetime import datetime, timezone

import pytest

from riff.data_governance import (
    approve_live_source,
    live_source_health_report,
    origin_audit,
    repair_origins,
)
from riff.db import connection, migrate
from riff.evidence import EvidenceSubmission, SourceType
from riff.evidence_repository import EvidenceRepository
from riff.ingestion_repository import IngestionRepository, RunStatus
from riff.live_worker import _live_evidence_ids


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    return value


def _submission(source_id, url, *, origin="LIVE"):
    return EvidenceSubmission(
        source_id=source_id,
        canonical_url=url,
        native_id=uuid.uuid4().hex,
        title="G48 provenance test",
        published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        raw_content="A bounded provenance test artifact.",
        data_origin=origin,
        origin_policy_version="g48-test-v1",
    )


@pytest.mark.postgres
def test_fixture_markers_are_classified_at_ingest(database_url):
    repo = EvidenceRepository(database_url)
    source = repo.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 fixture feed",
        canonical_root="https://fixture.example",
        source_id=f"g48-fixture-{uuid.uuid4().hex[:8]}",
    )
    result = repo.ingest(_submission(source.source_id, "https://fixture.example/item"))
    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT s.data_origin, si.data_origin, e.data_origin
               FROM sources s
               JOIN source_items si ON si.source_id=s.source_id
               JOIN evidence_versions e ON e.source_item_id=si.source_item_id
               WHERE e.evidence_id=%s""",
            (result.evidence_id,),
        ).fetchone()
    assert tuple(rows) == ("FIXTURE", "FIXTURE", "FIXTURE")
    assert _live_evidence_ids(database_url, (result.evidence_id,)) == []


@pytest.mark.postgres
def test_live_selection_requires_explicit_source_approval(database_url):
    repo = EvidenceRepository(database_url)
    source = repo.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 review-required feed",
        canonical_root="https://review.example",
        source_id=f"g48-review-{uuid.uuid4().hex[:8]}",
    )
    IngestionRepository(database_url).configure_source(source.source_id, "https://review.example/feed.xml", enabled=True)
    result = repo.ingest(_submission(source.source_id, "https://review.example/item"))
    assert _live_evidence_ids(database_url, (result.evidence_id,)) == []

    approved = approve_live_source(database_url, source_id=source.source_id, owner="g48-test")
    assert approved["data_origin"] == "LIVE"
    # Existing evidence remains untrusted until a reviewed fetch writes an
    # item under a LIVE source, preventing retroactive promotion of old data.
    result2 = repo.ingest(_submission(source.source_id, "https://review.example/new-item"))
    assert _live_evidence_ids(database_url, (result2.evidence_id,)) == [result2.evidence_id]


@pytest.mark.postgres
def test_repair_quarantines_legacy_live_rows_without_deleting(database_url):
    repo = EvidenceRepository(database_url)
    source = repo.create_source(
        SourceType.GITHUB,
        "G48 legacy source",
        canonical_root="https://legacy.example",
        source_id=f"legacy-source-{uuid.uuid4().hex[:8]}",
    )
    result = repo.ingest(_submission(source.source_id, "https://legacy.example/item"))
    # Simulate a legacy row written before the source-level trust boundary.
    with connection(database_url) as conn:
        conn.execute(
            "UPDATE evidence_versions SET data_origin='LIVE' WHERE evidence_id=%s",
            (result.evidence_id,),
        )
        conn.execute(
            "UPDATE source_items SET data_origin='LIVE' WHERE source_item_id=(SELECT source_item_id FROM evidence_versions WHERE evidence_id=%s)",
            (result.evidence_id,),
        )
    before = repo.get_evidence(result.evidence_id, include_raw=True)
    report = repair_origins(database_url, limit=5000)
    after = repo.get_evidence(result.evidence_id, include_raw=True)
    assert report["non_destructive"] is True
    assert before is not None and after is not None
    with connection(database_url) as conn:
        origin = conn.execute(
            "SELECT data_origin FROM evidence_versions WHERE evidence_id=%s",
            (result.evidence_id,),
        ).fetchone()[0]
        quarantines = conn.execute(
            "SELECT count(*) FROM data_quarantine_records WHERE row_key=%s",
            (result.evidence_id,),
        ).fetchone()[0]
    assert origin == "QUARANTINED"
    assert quarantines == 1
    assert _live_evidence_ids(database_url, (result.evidence_id,)) == []


@pytest.mark.postgres
def test_health_report_exposes_review_required_sources(database_url):
    repo = EvidenceRepository(database_url)
    source = repo.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 health source",
        canonical_root="https://health.example",
        source_id=f"g48-health-{uuid.uuid4().hex[:8]}",
    )
    IngestionRepository(database_url).configure_source(source.source_id, "https://health.example/feed.xml", enabled=True)
    report = live_source_health_report(database_url, limit=500)
    row = next(item for item in report["sources"] if item["source_id"] == source.source_id)
    assert row["state"] == "REVIEW_REQUIRED"
    audit = origin_audit(database_url, limit=500)
    assert any(item["source_id"] == source.source_id for item in audit["anomalies"]["unreviewed_sources"])


@pytest.mark.postgres
def test_health_report_exposes_metadata_and_distinguishes_failed_and_never_collected(database_url):
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    failed_source = evidence.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 failed health source",
        canonical_root="https://failed-health.example",
        source_id=f"g48-failed-health-{uuid.uuid4().hex[:8]}",
    )
    never_source = evidence.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 never collected source",
        canonical_root="https://never-health.example",
        source_id=f"g48-never-health-{uuid.uuid4().hex[:8]}",
    )
    for source, endpoint in (
        (failed_source, "https://failed-health.example/feed.xml"),
        (never_source, "https://never-health.example/feed.xml"),
    ):
        ingestion.configure_source(source.source_id, endpoint, enabled=True, cursor_kind="published_at")
        approve_live_source(database_url, source_id=source.source_id, owner="g48-health-owner")
    run = ingestion.start_run([failed_source.source_id], "g48-health-policy-v1")
    ingestion.finish_run(run.run_id, RunStatus.FAILED)

    report = live_source_health_report(database_url, limit=500)
    failed = next(item for item in report["sources"] if item["source_id"] == failed_source.source_id)
    never = next(item for item in report["sources"] if item["source_id"] == never_source.source_id)
    assert failed["state"] == "FAILED"
    assert failed["owner"] == "g48-health-owner"
    assert failed["canonical_root"] == "https://failed-health.example/"
    assert failed["fetch_policy"] == {
        "endpoint": "https://failed-health.example/feed.xml",
        "config_version": 1,
        "cursor_kind": "published_at",
    }
    assert failed["latest_health"]["status"] == "FAILED"
    assert failed["latest_health"]["policy_version"] == "g48-health-policy-v1"
    assert never["state"] == "NEVER_COLLECTED"
    assert never["latest_health"] is None


@pytest.mark.postgres
def test_collection_run_origin_is_resolved_from_approved_sources(database_url):
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 run-origin source",
        canonical_root="https://run-origin.example",
        source_id=f"run-origin-{uuid.uuid4().hex[:8]}",
    )
    ingestion.configure_source(source.source_id, "https://run-origin.example/feed.xml", enabled=True)
    approve_live_source(database_url, source_id=source.source_id, owner="g48-owner")
    run = ingestion.start_run([source.source_id], "g48-run-origin-v1")
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT data_origin, origin_owner, origin_run_id, origin_policy_version, origin_reason FROM collection_runs WHERE run_id=%s",
            (run.run_id,),
        ).fetchone()
    assert tuple(row) == ("LIVE", "g48-owner", run.run_id, "g48-run-origin-v1", None)


@pytest.mark.postgres
def test_replay_can_scope_to_source_or_collection_run(database_url):
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source_ids = []
    evidence_ids = []
    for label in ("one", "two"):
        source = evidence.create_source(
            SourceType.TECHNICAL_WRITING,
            f"G48 scoped source {label}",
            canonical_root=f"https://scoped-{label}.example",
            source_id=f"scoped-{label}-{uuid.uuid4().hex[:8]}",
        )
        ingestion.configure_source(source.source_id, f"https://scoped-{label}.example/feed.xml", enabled=True)
        approve_live_source(database_url, source_id=source.source_id, owner="g48-owner")
        source_ids.append(source.source_id)
        result = evidence.ingest(_submission(source.source_id, f"https://scoped-{label}.example/item"))
        evidence_ids.append(result.evidence_id)
    run = ingestion.start_run([source_ids[0]], "g48-scope-v1")
    ingestion.record_item_result(run.run_id, source_ids[0], "STORED", evidence_id=evidence_ids[0])
    assert _live_evidence_ids(database_url, source_ids=source_ids[:1]) == [evidence_ids[0]]
    assert _live_evidence_ids(database_url, collection_run_id=run.run_id) == [evidence_ids[0]]


@pytest.mark.postgres
def test_audit_reason_codes_distinguish_disabled_sources(database_url):
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(
        SourceType.TECHNICAL_WRITING,
        "G48 audit reason source",
        canonical_root="https://audit-reason.example",
        source_id=f"audit-reason-{uuid.uuid4().hex[:8]}",
    )
    ingestion.configure_source(source.source_id, "https://audit-reason.example/feed.xml", enabled=True)
    approve_live_source(database_url, source_id=source.source_id, owner="g48-owner")
    result = evidence.ingest(_submission(source.source_id, "https://audit-reason.example/item"))
    ingestion.set_source_enabled(source.source_id, False)
    audit = origin_audit(database_url, limit=500)
    row = next(item for item in audit["anomalies"]["live_evidence_without_trusted_source"] if item["evidence_id"] == result.evidence_id)
    assert row["reason_code"] == "DISABLED_SOURCE"


@pytest.mark.postgres
def test_repair_classifies_and_disables_generated_test_sources(database_url):
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(
        SourceType.TECHNICAL_WRITING,
        "Generated replay source",
        canonical_root="https://generated-replay.example",
        source_id=f"g48-generated-test-{uuid.uuid4().hex[:8]}",
    )
    ingestion.configure_source(source.source_id, "https://generated-replay.example/feed.xml", enabled=True)
    result = evidence.ingest(_submission(source.source_id, "https://generated-replay.example/item"))
    report = repair_origins(database_url, limit=5000)
    assert source.source_id in report["test_source_ids"]
    with connection(database_url) as conn:
        row = conn.execute(
            """SELECT s.data_origin, s.enabled, c.enabled, si.data_origin, e.data_origin
               FROM sources s LEFT JOIN ingestion_source_configs c ON c.source_id=s.source_id
               JOIN source_items si ON si.source_id=s.source_id
               JOIN evidence_versions e ON e.source_item_id=si.source_item_id
               WHERE s.source_id=%s AND e.evidence_id=%s""",
            (source.source_id, result.evidence_id),
        ).fetchone()
    assert tuple(row) == ("TEST", False, False, "TEST", "TEST")
