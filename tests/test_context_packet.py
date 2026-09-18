import json
import os
from pathlib import Path

import pytest

from riff.context_packet import ContextPacketRepository
from riff.db import connection, migrate
from riff.evidence_repository import EvidenceRepository
from riff.raw_signal_ingestion import RawSignalIngestionRunner, load_fixture
from riff.context_packet import select_context_packet


FIXTURE = Path(__file__).parent / "fixtures" / "context" / "g39-packet-v1.json"


def test_context_packet_is_bounded_diverse_and_redacted():
    payload = json.loads(FIXTURE.read_text())
    result = select_context_packet(payload["query"], payload["candidates"], project=payload["project"], goal=payload["goal"], limit=3, char_budget=3000)
    assert {item["evidence_id"] for item in result["evidence"]} == {"incident-1", "paper-1"}
    assert "mirror-1" in {item["evidence_id"] for item in result["omitted"]}
    assert "secret-value" not in json.dumps(result)
    assert result["usage"]["character_count"] <= 3000
    assert result["project_goal_context"][0]["reference"] == "verbal-agency/caduceus"
    assert "project_goal_fit" in next(item for item in result["evidence"] if item["evidence_id"] == "incident-1")["selection_reasons"]
    assert all("raw_content" not in item for item in result["evidence"])


def test_context_packet_expansion_avoids_seen_receipts_and_reports_unknowns():
    payload = json.loads(FIXTURE.read_text())
    first = select_context_packet(payload["query"], payload["candidates"], limit=1, char_budget=3000)
    second = select_context_packet(payload["query"], payload["candidates"], limit=2, char_budget=3000, seen_evidence_ids=[item["evidence_id"] for item in first["evidence"]], page=0)
    assert not ({item["evidence_id"] for item in first["evidence"]} & {item["evidence_id"] for item in second["evidence"]})


def test_context_packet_empty_query_is_rejected():
    try:
        select_context_packet("", [])
    except ValueError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("empty query should fail closed")


@pytest.mark.postgres
def test_context_packet_repository_returns_receipts_without_raw_bodies():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    fixture = load_fixture(Path(__file__).parent / "fixtures" / "raw_signals" / "g38-v1.json")
    runner = RawSignalIngestionRunner(EvidenceRepository(database_url))
    stored = runner.ingest(fixture, fixture_mode=True, owner="g39-context-test")
    evidence_ids = [item["evidence_id"] for item in stored["results"]]
    try:
        packet = ContextPacketRepository(database_url).build("agent recovery", limit=3)
        assert packet["evidence"]
        assert all("raw_content" not in item for item in packet["evidence"])
        assert packet["usage"]["estimated_context_tokens"] >= packet["usage"]["estimated_input_tokens"]
    finally:
        with connection(database_url) as conn:
            conn.execute("DELETE FROM retrievals WHERE evidence_id = ANY(%s)", (evidence_ids,))
            conn.execute("DELETE FROM evidence_versions WHERE evidence_id = ANY(%s)", (evidence_ids,))
            source_ids = [item.source_id for item in fixture["signals"]]
            conn.execute("DELETE FROM source_items WHERE source_id = ANY(%s)", (source_ids,))
            conn.execute("DELETE FROM sources WHERE source_id = ANY(%s)", (source_ids,))
