import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.evidence import EvidenceSubmission, SourceType
from riff.evidence_repository import EvidenceRepository
from riff.data_governance import approve_live_source
from riff.github_ingestion import GitHubResponse
from riff.ingestion import FeedResponse
from riff.ingestion_repository import IngestionRepository
from riff.live_worker import LiveSourceCollector, run_live_pipeline


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "feeds"


class FixtureFeedFetcher:
    def fetch(self, endpoint: str) -> FeedResponse:
        return FeedResponse(
            (FIXTURE_DIR / "initial.xml").read_bytes(),
            datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
            endpoint,
        )


class UnusedGitHubFetcher:
    def fetch(self, path: str, *, params=None) -> GitHubResponse:
        raise AssertionError(f"unexpected GitHub request: {path}")


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    return value


@pytest.mark.postgres
def test_live_worker_composes_enabled_writing_source_and_surfaces_candidate(database_url):
    source_id = f"g40-live-writing-source-{uuid.uuid4().hex[:10]}"
    run_date = date(2099, 1, 1)
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "G40 approved live writing", canonical_root="https://example.com", source_id=source_id)
    ingestion.configure_source(source.source_id, "https://example.com/feed.xml", enabled=True)
    approve_live_source(database_url, source_id=source_id, owner="g40-test")
    collector = LiveSourceCollector(
        database_url,
        source_ids=[source_id],
        feed_fetcher=FixtureFeedFetcher(),
        github_fetcher=UnusedGitHubFetcher(),
        job_policy_path="config/job_sources.json",
    )
    policy_version = f"g40-test-v1-{uuid.uuid4().hex[:10]}"

    report = run_live_pipeline(
        database_url,
        run_date=run_date,
        policy_version=policy_version,
        collector=collector,
    )

    assert report["mode"] == "live"
    assert report["status"] == "EMPTY"
    assert report["live_evidence_count"] == 2
    assert report["candidate_count"] >= 1
    assert report["outcome_classification"] == "EMPTY"
    assert report["evidence_outcome"] == "INSUFFICIENT_EVIDENCE"
    assert any(item["source_type"] == "TECHNICAL_WRITING" and item["status"] == "SUCCEEDED" for item in report["source_outcomes"])
    assert [stage["status"] for stage in report["stages"]] == ["COMPLETE"] * 7
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM daily_riff_runs WHERE run_date = %s AND generation_policy_version = %s", (run_date, policy_version)).fetchone()[0] == 1

    second = run_live_pipeline(
        database_url,
        run_date=run_date,
        policy_version=policy_version,
        resume=True,
        collector=collector,
    )
    assert second["noop"] is True and second["run_id"] == report["run_id"]

    ingestion.set_source_enabled(source_id, False)
    disabled = run_live_pipeline(
        database_url,
        run_date=date(2099, 1, 2),
        policy_version=f"g40-disabled-{uuid.uuid4().hex[:10]}",
        collector=collector,
    )
    assert disabled["status"] == "EMPTY"
    assert disabled["source_outcomes"][0]["status"] == "SKIPPED"


@pytest.mark.postgres
def test_live_replay_reuses_persisted_evidence_without_collecting(database_url):
    source_id = f"g43-live-replay-source-{uuid.uuid4().hex[:10]}"
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "G43 approved live replay", canonical_root="https://example.com", source_id=source_id)
    ingestion.configure_source(source.source_id, "https://example.com/replay.xml", enabled=True)
    approve_live_source(database_url, source_id=source_id, owner="g43-test")
    collector = LiveSourceCollector(
        database_url,
        source_ids=[source_id],
        feed_fetcher=FixtureFeedFetcher(),
        github_fetcher=UnusedGitHubFetcher(),
        job_policy_path="config/job_sources.json",
    )
    first = run_live_pipeline(database_url, run_date=date(2099, 2, 1), policy_version=f"g43-fetch-{uuid.uuid4().hex[:10]}", collector=collector)
    with connection(database_url) as conn:
        ids = tuple(row[0] for row in conn.execute("SELECT e.evidence_id FROM evidence_versions e JOIN source_items si ON si.source_item_id = e.source_item_id WHERE si.source_id = %s AND e.data_origin = 'LIVE'", (source_id,)).fetchall())
    assert first["live_evidence_count"] == 2
    replay = run_live_pipeline(
        database_url,
        run_date=date(2099, 2, 2),
        policy_version=f"g43-replay-{uuid.uuid4().hex[:10]}",
        replay_evidence_ids=ids,
        replay_since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert replay["source_outcomes"][0]["source_type"] == "LIVE_REPLAY"
    assert replay["live_evidence_count"] == 2
    assert replay["outcome_classification"] in {"EMPTY", "INSUFFICIENT_EVIDENCE"}


@pytest.mark.postgres
def test_live_replay_requires_two_independent_roots_for_publication(database_url):
    evidence = EvidenceRepository(database_url)
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "G48 single-root live source", canonical_root="https://single-root.example")
    ingestion = IngestionRepository(database_url)
    ingestion.configure_source(source.source_id, "https://single-root.example/feed", enabled=True)
    approve_live_source(database_url, source_id=source.source_id, owner="g48-test")
    result = evidence.ingest(
        EvidenceSubmission(
            source_id=source.source_id,
            canonical_url="https://single-root.example/durable-agent-execution",
            native_id="g48-single-root",
            title="Durable agent execution",
            published_at=datetime(2026, 10, 2, 12, tzinfo=timezone.utc),
            raw_content="Teams demonstrate resumable workflow recovery with durable execution and evaluation.",
            data_origin="LIVE",
            origin_run_id="g48-recorded-live",
            origin_policy_version="g48-test-v1",
        )
    )
    second = evidence.ingest(
        EvidenceSubmission(
            source_id=source.source_id,
            canonical_url="https://single-root.example/recovery",
            native_id="g48-single-root-second",
            title="Workflow recovery",
            published_at=datetime(2026, 10, 2, 13, tzinfo=timezone.utc),
            raw_content="Teams demonstrate resumable workflow recovery with durable execution and evaluation.",
            data_origin="LIVE",
            origin_run_id="g48-recorded-live",
            origin_policy_version="g48-test-v1",
        )
    )

    report = run_live_pipeline(
        database_url,
        run_date=date(2026, 10, 2),
        policy_version=f"g48-single-root-{uuid.uuid4().hex[:10]}",
        replay_evidence_ids=(result.evidence_id, second.evidence_id),
        replay_since=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )

    assert report["status"] == "EMPTY"
    assert report["candidate_count"] >= 1
    assert report["outcome_classification"] in {"EMPTY", "INSUFFICIENT_EVIDENCE"}
    assert report["publication_gate"]["required_independent_roots"] == 2
    assert report["publication_gate"]["empty_reason"]
    assert report["stages"][-1]["output_count"] == 0


@pytest.mark.postgres
def test_live_replay_publishes_when_recent_evidence_is_independent(database_url):
    evidence = EvidenceRepository(database_url)
    evidence_ids = []
    for source_type, name, root in (
        (SourceType.TECHNICAL_WRITING, "G43 writing evidence", "https://writing.example"),
        (SourceType.GITHUB, "G43 GitHub evidence", "https://github.example"),
    ):
        source = evidence.create_source(source_type, name, canonical_root=root)
        ingestion = IngestionRepository(database_url)
        ingestion.configure_source(source.source_id, f"{root}/feed", enabled=True)
        approve_live_source(database_url, source_id=source.source_id, owner="g43-test")
        result = evidence.ingest(
            EvidenceSubmission(
                source_id=source.source_id,
                canonical_url=f"{root}/durable-agent-execution",
                native_id=f"g43-{source_type.value.lower()}",
                title="Durable agent execution",
                published_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
                raw_content="Teams demonstrate resumable workflow recovery with durable execution and evaluation.",
                data_origin="LIVE",
                origin_run_id="g43-recorded-live",
                origin_policy_version="g43-test-v1",
            )
        )
        evidence_ids.append(result.evidence_id)

    report = run_live_pipeline(
        database_url,
        run_date=date(2026, 10, 1),
        policy_version=f"g43-independent-{uuid.uuid4().hex[:10]}",
        replay_evidence_ids=tuple(evidence_ids),
        replay_since=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )

    assert report["status"] == "SUCCEEDED"
    assert report["candidate_count"] >= 1
    assert report["outcome_classification"] == "SUCCEEDED"
