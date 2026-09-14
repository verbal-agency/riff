import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from riff.capability_evaluation import evaluate_fixture
from riff.capabilities import CapabilityRepository, DeterministicNormalizer, NormalizationService
from riff.db import connection, migrate
from riff.evidence import EvidenceSubmission, SourceType
from riff.evidence_repository import EvidenceRepository
from riff.receipts import EvidenceReceipt, ReceiptRepository


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "capabilities"


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM signal_explanations")
        conn.execute("DELETE FROM signal_features")
        conn.execute("DELETE FROM candidate_signals")
        conn.execute("DELETE FROM correlation_members")
        conn.execute("DELETE FROM correlation_groups")
        conn.execute("DELETE FROM rank_runs")
        conn.execute("DELETE FROM rank_configs")
        conn.execute("DELETE FROM gap_assessments")
        conn.execute("DELETE FROM profile_history")
        conn.execute("DELETE FROM experience_ledger")
        conn.execute("DELETE FROM profile_evidence")
        conn.execute("DELETE FROM normalization_decisions")
        conn.execute("DELETE FROM capability_relationships")
        conn.execute("DELETE FROM capability_mappings")
        conn.execute("DELETE FROM capability_aliases")
        conn.execute("DELETE FROM capability_patterns")
        conn.execute("DELETE FROM capability_concepts")
        conn.execute("DELETE FROM technologies")
        conn.execute("DELETE FROM capabilities")
    evidence = EvidenceRepository(database_url)
    receipts = ReceiptRepository(database_url)
    graph = CapabilityRepository(database_url)
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "capability-fixtures")
    return database_url, evidence, receipts, graph, source


def _receipt(evidence, receipts, source, *, capabilities, technologies):
    result = evidence.ingest(
        EvidenceSubmission(
            source_id=source.source_id,
            canonical_url=f"https://example.com/{os.urandom(4).hex()}",
            title="Capability fixture",
            raw_content="checkpoint recovery and workflow replay are described here.",
        )
    )
    record = evidence.get_evidence(result.evidence_id, include_raw=True)
    receipt = EvidenceReceipt(
        receipt_id=os.urandom(16).hex(), evidence_id=record.evidence_id, content_hash=record.content_hash,
        extractor_version="fixture-v1", schema_version=1, status="SUCCEEDED", summary=record.raw_content,
        relevant_spans=[{"span_id": "s1", "start": 0, "end": len(record.raw_content), "excerpt": record.raw_content}],
        capability_candidates=list(capabilities), technology_candidates=list(technologies),
        claims=[{"text": "Observed", "span_ids": ["s1"], "claim_type": "OBSERVATION", "uncertainty": {}}],
        signal_strength={}, source_metadata={"evidence_id": record.evidence_id, "source_id": record.source_id}, uncertainty={},
    )
    receipts.store(receipt)
    return receipt


@pytest.mark.postgres
def test_durable_aliases_and_negative_concepts_remain_distinct(graph):
    _, evidence, receipts, repository, source = graph
    receipt = _receipt(
        evidence, receipts, source,
        capabilities=["checkpoint recovery", "resumable agents", "workflow replay", "agent memory", "workflow persistence"],
        technologies=["Temporal"],
    )
    summary = NormalizationService(receipts, repository, DeterministicNormalizer()).normalize([receipt.receipt_id])
    names = {mapping.candidate_text: mapping.entity_id for mapping in summary.mappings if mapping.entity_type == "CAPABILITY"}
    assert summary.processed == 1
    with connection(graph[0]) as conn:
        rows = conn.execute("SELECT name FROM capabilities ORDER BY name").fetchall()
    assert {row[0] for row in rows} == {"durable execution", "agent memory", "workflow persistence"}
    assert len({names["checkpoint recovery"], names["resumable agents"], names["workflow replay"]}) == 1


@pytest.mark.postgres
def test_framework_fragmentation_strengthens_one_capability(graph):
    _, evidence, receipts, repository, source = graph
    first = _receipt(evidence, receipts, source, capabilities=["durable execution"], technologies=["LangGraph"])
    second = _receipt(evidence, receipts, source, capabilities=["workflow replay"], technologies=["Temporal"])
    service = NormalizationService(receipts, repository, DeterministicNormalizer())
    service.normalize([first.receipt_id, second.receipt_id])
    with connection(graph[0]) as conn:
        capabilities = conn.execute("SELECT capability_id, name FROM capabilities").fetchall()
        relationships = conn.execute("SELECT capability_id, technology_id FROM capability_relationships").fetchall()
    assert [row[1] for row in capabilities] == ["durable execution"]
    assert len(relationships) == 2


@pytest.mark.postgres
def test_review_accept_remap_split_and_undo_preserve_provenance(graph):
    _, evidence, receipts, repository, source = graph
    receipt = _receipt(evidence, receipts, source, capabilities=["workflow replay"], technologies=[])
    service = NormalizationService(receipts, repository, DeterministicNormalizer())
    mapping = service.normalize([receipt.receipt_id]).mappings[0]
    accepted = repository.review(mapping.mapping_id, "ACCEPT", actor="reviewer", reason="fixture confirmation")
    target = repository.upsert_capability("replay orchestration")
    remapped = repository.review(accepted.mapping_id, "REMAP", actor="reviewer", reason="more precise label", entity_id=target.capability_id)
    split = repository.split(remapped.mapping_id, ["checkpoint recovery", "workflow replay"], actor="reviewer", reason="two distinct patterns")
    assert remapped.status == "ACCEPTED"
    assert {item.candidate_text for item in split} == {"workflow replay"}
    restored = repository.review(remapped.mapping_id, "UNDO", actor="reviewer", reason="revert split")
    assert restored.status == "ACCEPTED" and restored.entity_id == target.capability_id
    assert all(item.receipt_id == receipt.receipt_id for item in repository.list_mappings(receipt_id=receipt.receipt_id))
    assert len(repository.inspect_capability(target.capability_id).decisions) >= 2


@pytest.mark.postgres
def test_technology_relationships_are_many_to_many_and_reruns_are_cached(graph):
    _, evidence, receipts, repository, source = graph
    first = _receipt(evidence, receipts, source, capabilities=["durable execution"], technologies=["Temporal"])
    second = _receipt(evidence, receipts, source, capabilities=["workflow persistence"], technologies=["Temporal"])
    service = NormalizationService(receipts, repository, DeterministicNormalizer())
    initial = service.normalize([first.receipt_id, second.receipt_id])
    cached = service.normalize([first.receipt_id, second.receipt_id])
    assert (initial.processed, cached.cached) == (2, 2)
    with connection(graph[0]) as conn:
        counts = conn.execute("SELECT count(DISTINCT capability_id), count(DISTINCT technology_id), count(*) FROM capability_relationships").fetchone()
    assert counts == (2, 1, 2)


def test_capability_evaluation_reports_under_and_over_merging_separately():
    report = evaluate_fixture(FIXTURE_DIR / "normalization.json")
    assert report["cases"] == 6
    assert report["under_merging"]["correct"] == 5
    assert report["over_merging"]["correct"] == 5
    assert report["under_merging"]["failures"] == [{"id": "under-merge-example", "missing": ["agent memory"]}]
    assert report["over_merging"]["failures"] == [{"id": "over-merge-example", "extra": ["agent memory"]}]
