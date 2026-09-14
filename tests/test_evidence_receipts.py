import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from riff.db import migrate
from riff.evidence import EvidenceRecord, EvidenceSubmission, SourceType
from riff.evidence_repository import EvidenceRepository
from riff.receipt_evaluation import evaluate_labeled_fixture
from riff.receipts import (
    ReceiptProcessSummary,
    ReceiptProcessor,
    ReceiptRepository,
    ReceiptValidationError,
    TransientExtractionError,
    validate_receipt_output,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "receipts"


class StaticExtractor:
    def __init__(self, version="fixture-v1", *, invalid=False, transient=False):
        self.version = version
        self.invalid = invalid
        self.transient = transient
        self.calls = 0

    def extract(self, evidence):
        self.calls += 1
        if self.transient:
            raise TransientExtractionError("provider timeout")
        excerpt = (evidence.raw_content or "")[:40]
        end = len(excerpt)
        if self.invalid:
            end += 1
        return {
            "summary": excerpt,
            "relevant_spans": [{"span_id": "s1", "start": 0, "end": end, "excerpt": excerpt}],
            "capability_candidates": ["test capability"],
            "technology_candidates": ["test technology"],
            "claims": [{"text": "Observed claim", "span_ids": ["s1"], "claim_type": "OBSERVATION", "uncertainty": {}}],
            "signal_strength": {"independence": "unknown"},
            "source_metadata": {"evidence_id": evidence.evidence_id, "source_id": evidence.source_id, "source_type": evidence.source_type.value},
            "uncertainty": {},
        }


@pytest.fixture()
def evidence_records():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    repository = EvidenceRepository(database_url)
    records = []
    for source_type in (SourceType.TECHNICAL_WRITING, SourceType.GITHUB, SourceType.JOBS):
        source = repository.create_source(source_type, f"receipt-{source_type.value}")
        result = repository.ingest(
            EvidenceSubmission(
                source_id=source.source_id,
                canonical_url=f"https://example.com/{source_type.value.lower()}",
                native_id=f"receipt-{source_type.value.lower()}",
                title=f"{source_type.value} evidence",
                published_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
                raw_content=f"{source_type.value} evidence supports replayable workflows.",
            )
        )
        records.append(result.evidence_id)
    return database_url, repository, records


@pytest.mark.postgres
def test_receipts_cover_all_source_types(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    receipts = ReceiptRepository(database_url)
    processor = ReceiptProcessor(evidence, receipts, StaticExtractor())
    summary = processor.process(evidence_ids)
    assert isinstance(summary, ReceiptProcessSummary)
    assert summary.processed == 3
    assert {item.source_metadata["source_type"] for item in (receipts.get_receipt(result.receipt_id) for result in summary.results)} == {"TECHNICAL_WRITING", "GITHUB", "JOBS"}


@pytest.mark.postgres
def test_spans_resolve_to_raw_evidence(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    receipts = ReceiptRepository(database_url)
    summary = ReceiptProcessor(evidence, receipts, StaticExtractor()).process(evidence_ids[:1])
    receipt = receipts.get_receipt(summary.results[0].receipt_id)
    raw = evidence.get_evidence(receipt.evidence_id, include_raw=True).raw_content
    span = receipt.relevant_spans[0]
    assert raw[span["start"] : span["end"]] == span["excerpt"]


@pytest.mark.postgres
def test_unchanged_evidence_is_not_reprocessed(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    extractor = StaticExtractor()
    processor = ReceiptProcessor(evidence, ReceiptRepository(database_url), extractor)
    assert processor.process(evidence_ids[:1]).processed == 1
    cached = processor.process(evidence_ids[:1])
    assert (cached.cached, extractor.calls) == (1, 1)


@pytest.mark.postgres
def test_extractor_version_creates_new_receipt(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    receipts = ReceiptRepository(database_url)
    processor = ReceiptProcessor(evidence, receipts, StaticExtractor("fixture-v1"))
    processor.process(evidence_ids[:1])
    processor = ReceiptProcessor(evidence, receipts, StaticExtractor("fixture-v2"))
    processor.process(evidence_ids[:1])
    assert len(receipts.list_receipts(evidence_id=evidence_ids[0])) == 2


@pytest.mark.postgres
def test_invalid_and_transient_outputs_are_inspectable(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    receipts = ReceiptRepository(database_url)
    invalid = ReceiptProcessor(evidence, receipts, StaticExtractor(invalid=True)).process(evidence_ids[:1])
    assert invalid.failed_validation == 1
    transient_extractor = StaticExtractor(transient=True)
    transient = ReceiptProcessor(evidence, receipts, transient_extractor).process(evidence_ids[1:2])
    assert transient.failed_transient == 1
    retry = ReceiptProcessor(evidence, receipts, StaticExtractor()).process(evidence_ids[1:2])
    assert retry.processed == 1


@pytest.mark.postgres
def test_receipt_retrieval_does_not_load_raw_by_default(evidence_records):
    database_url, evidence, evidence_ids = evidence_records
    receipts = ReceiptRepository(database_url)
    result = ReceiptProcessor(evidence, receipts, StaticExtractor()).process(evidence_ids[:1]).results[0]
    receipt = receipts.get_receipt(result.receipt_id, include_raw=True)
    assert not hasattr(receipt, "raw_content")
    assert evidence.get_evidence(receipt.evidence_id).raw_content is None


def test_evaluation_report_scores_each_field():
    report = evaluate_labeled_fixture(FIXTURE_DIR / "labeled.json")
    assert report["examples"] == 3
    assert all(score["accuracy"] == 1.0 for score in report["fields"].values())


def test_missing_receipt_fields_are_rejected():
    evidence = EvidenceRecord(
        evidence_id="evidence-1",
        source_item_id="item-1",
        source_id="source-1",
        source_type=SourceType.GITHUB,
        source_name="fixture",
        canonical_url="https://example.com/item-1",
        native_id="item-1",
        title="Fixture",
        content_hash="a" * 64,
        retrieved_at=datetime.now(timezone.utc),
        published_at=None,
        schema_version=1,
        raw_content="grounded text",
        snapshot_ref=None,
        previous_evidence_id=None,
    )
    with pytest.raises(ReceiptValidationError, match="missing fields"):
        validate_receipt_output(evidence, {}, "fixture-v1")
