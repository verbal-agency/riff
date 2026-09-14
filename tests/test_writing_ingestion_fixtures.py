import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from riff.db import migrate
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.ingestion import FeedResponse, PermanentFeedError, TransientFeedError
from riff.ingestion_repository import IngestionRepository, ItemOutcome, RunStatus
from riff.writing_ingestion import WritingIngestionRunner


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "feeds"


class FixtureFetcher:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def fetch(self, _endpoint):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


class TerminatingEvidenceRepository:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def ingest(self, submission):
        result = self.delegate.ingest(submission)
        self.calls += 1
        if self.calls == 1:
            raise KeyboardInterrupt("simulated process termination after evidence commit")
        return result


def _response(filename: str) -> FeedResponse:
    return FeedResponse(
        body=(FIXTURE_DIR / filename).read_bytes(),
        fetched_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
        final_url="https://example.com/feed.xml",
    )


@pytest.fixture()
def repositories():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    return IngestionRepository(database_url), EvidenceRepository(database_url)


def _configured_source(ingestion, evidence, *, enabled=True):
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, f"fixture-{uuid4()}")
    configured = ingestion.configure_source(
        source.source_id,
        "https://example.com/feed.xml",
        enabled=enabled,
    )
    return configured


@pytest.mark.postgres
def test_fixture_feed_three_passes(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)

    first = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("initial.xml"))).run(
        source_ids=[source.source_id]
    )
    unchanged = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("initial.xml"))).run(
        source_ids=[source.source_id]
    )
    incremented = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("incremented.xml"))).run(
        source_ids=[source.source_id]
    )

    assert (first.status, first.stored) == (RunStatus.SUCCEEDED, 2)
    assert (unchanged.status, unchanged.stored, unchanged.duplicates) == (RunStatus.SUCCEEDED, 0, 0)
    assert (incremented.status, incremented.stored) == (RunStatus.SUCCEEDED, 2)
    assert evidence.source_item_count(source.source_id) == 3
    assert ingestion.get_cursor(source.source_id, source.cursor_kind)


@pytest.mark.postgres
def test_malformed_item_yields_partial_run(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)
    summary = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("malformed-entry.xml"))).run(
        source_ids=[source.source_id]
    )
    assert summary.status == RunStatus.PARTIAL
    assert summary.stored == 1
    assert summary.failed_permanent == 1
    assert ingestion.get_cursor(source.source_id, source.cursor_kind)


@pytest.mark.postgres
def test_retryable_timeout(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)
    fetcher = FixtureFetcher(error=TransientFeedError("timeout"))
    summary = WritingIngestionRunner(ingestion, evidence, fetcher).run(source_ids=[source.source_id])
    assert summary.status == RunStatus.FAILED
    assert summary.failed_transient == 1
    assert ingestion.get_cursor(source.source_id, source.cursor_kind) is None
    assert fetcher.calls == 1
    retry = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("initial.xml"))).run(
        source_ids=[source.source_id]
    )
    assert (retry.status, retry.stored) == (RunStatus.SUCCEEDED, 2)


@pytest.mark.postgres
def test_permanent_parse_failure(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)
    fetcher = FixtureFetcher(error=PermanentFeedError("unsupported document"))
    summary = WritingIngestionRunner(ingestion, evidence, fetcher).run(source_ids=[source.source_id])
    assert summary.status == RunStatus.FAILED
    assert summary.failed_permanent == 1
    assert ingestion.get_cursor(source.source_id, source.cursor_kind) is None


@pytest.mark.postgres
def test_source_registry_enable_disable(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence, enabled=False)
    fetcher = FixtureFetcher(_response("initial.xml"))
    summary = WritingIngestionRunner(ingestion, evidence, fetcher).run(source_ids=[source.source_id])
    assert summary.status == RunStatus.SUCCEEDED
    assert summary.skipped == 1
    assert fetcher.calls == 0


@pytest.mark.postgres
def test_cursor_advances_only_after_evidence_commit(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)
    terminating = TerminatingEvidenceRepository(evidence)
    runner = WritingIngestionRunner(ingestion, terminating, FixtureFetcher(_response("initial.xml")))
    with pytest.raises(KeyboardInterrupt):
        runner.run(source_ids=[source.source_id])
    assert ingestion.get_cursor(source.source_id, source.cursor_kind) is None

    retry = WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("initial.xml"))).run(
        source_ids=[source.source_id]
    )
    assert (retry.status, retry.stored, retry.duplicates) == (RunStatus.SUCCEEDED, 1, 1)
    assert ingestion.get_cursor(source.source_id, source.cursor_kind)


@pytest.mark.postgres
def test_writing_evidence_is_traceable_and_searchable(repositories):
    ingestion, evidence = repositories
    source = _configured_source(ingestion, evidence)
    WritingIngestionRunner(ingestion, evidence, FixtureFetcher(_response("initial.xml"))).run(
        source_ids=[source.source_id]
    )
    found = evidence.search(source_type=SourceType.TECHNICAL_WRITING, text="replay")
    assert any(item.source_id == source.source_id for item in found)
