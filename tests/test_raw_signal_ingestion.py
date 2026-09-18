import json
import os
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.evidence_repository import EvidenceRepository
from riff.raw_signal_ingestion import RawSignalError, RawSignalIngestionRunner, load_fixture, load_source_manifest


FIXTURE = Path(__file__).parent / "fixtures" / "raw_signals" / "g38-v1.json"


def test_raw_signal_fixture_covers_classes_and_discloses_leads():
    payload = load_fixture(FIXTURE)
    report = RawSignalIngestionRunner(EvidenceRepository("postgresql://offline/unused")).validate(payload)
    assert {"INCIDENT_REPORT", "SCIENTIFIC_PAPER", "BENCHMARK", "GITHUB_DISCUSSION"} <= set(report["classes"])
    assert report["evidence_roles"]["USER_LEAD"] == 1


def test_reviewed_source_manifest_covers_new_classes_without_enabling_network_access():
    manifest = load_source_manifest(Path("config/raw_signal_sources.json"))
    assert len(manifest["sources"]) >= 5
    assert all(item["enabled"] is False for item in manifest["sources"])


def test_malformed_signal_and_unknown_class_fail_closed(tmp_path):
    payload = {"schema_version": 1, "fixture_id": "bad", "signals": [{"signal_id": "x"}]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(RawSignalError, match="missing"):
        load_fixture(path)


@pytest.mark.postgres
def test_raw_signal_ingestion_replays_idempotently_and_keeps_lead_uncertainty():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    payload = load_fixture(FIXTURE)
    runner = RawSignalIngestionRunner(EvidenceRepository(database_url))
    first = runner.ingest(payload, fixture_mode=True, owner="g38-test")
    second = runner.ingest(payload, fixture_mode=True, owner="g38-test")
    assert first["stored"] == len(payload["signals"])
    assert second["stored"] == 0 and second["duplicates"] == len(payload["signals"])
    lead = next(item for item in first["results"] if item["signal_id"] == "lead-001")
    assert "secondary_or_user_supplied_signal_requires_source_validation" in lead["uncertainty"]
    with connection(database_url) as conn:
        ids = [item["evidence_id"] for item in first["results"]]
        conn.execute("DELETE FROM retrievals WHERE evidence_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM evidence_versions WHERE evidence_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM source_items WHERE source_id = ANY(%s)", ([f"source-{name}" for name in ("incident-lab", "paper2tool", "agent-benchmark", "agent-discussion", "operator-lead")],))
        conn.execute("DELETE FROM sources WHERE source_id = ANY(%s)", ([f"source-{name}" for name in ("incident-lab", "paper2tool", "agent-benchmark", "agent-discussion", "operator-lead")],))
