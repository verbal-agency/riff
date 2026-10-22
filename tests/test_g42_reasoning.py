import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from riff.db import migrate
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.ingestion import FeedResponse
from riff.ingestion_repository import IngestionRepository
from riff.live_worker import LiveSourceCollector, run_live_pipeline
from riff.reasoning import BoundedReasoningProvider, RecordedReasoningProvider, ReasoningLimits
from riff.github_ingestion import GitHubResponse


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "feeds"


class FixtureFeedFetcher:
    def fetch(self, endpoint: str) -> FeedResponse:
        return FeedResponse((FIXTURE_DIR / "initial.xml").read_bytes(), datetime(2026, 9, 30, 12, tzinfo=timezone.utc), endpoint)


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
def test_live_worker_records_reasoning_telemetry(database_url):
    source_id = f"g42-reasoning-source-{uuid.uuid4().hex[:10]}"
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(SourceType.TECHNICAL_WRITING, "G42 reasoning fixture", source_id=source_id)
    ingestion.configure_source(source.source_id, "https://example.com/g42.xml", enabled=True)
    collector = LiveSourceCollector(database_url, source_ids=[source_id], feed_fetcher=FixtureFeedFetcher(), github_fetcher=UnusedGitHubFetcher(), job_policy_path="config/job_sources.json")
    provider = BoundedReasoningProvider(RecordedReasoningProvider.from_path("tests/fixtures/reasoning/g42-recorded.json"), model=None, context_policy_version="g42-context-v1", limits=ReasoningLimits(max_calls=5, max_input_tokens=10000, max_output_tokens=10000))
    report = run_live_pipeline(database_url, run_date=date(2099, 3, 1), policy_version=f"g42-reasoning-{uuid.uuid4().hex[:10]}", collector=collector, reasoning_provider=provider)
    assert report.get("reasoning", {}).get("model") == "recorded-reviewer-v1"
    assert report["reasoning"]["outcome"] in {"PUBLISHED", "VALID_EMPTY"}
    assert report["reasoning"]["context_policy_version"] == "g42-context-v1"
    assert report["reasoning"]["input_fingerprint"]
    assert report["stages"][-1]["token_count"] >= 0
