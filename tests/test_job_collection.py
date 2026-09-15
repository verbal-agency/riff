import json
from dataclasses import replace
from pathlib import Path

import pytest

from riff.job_fetch import FixtureJobFetcher, decompose_listing, validate_target_url
from riff.evidence_repository import EvidenceRepository
from riff.ingestion_repository import IngestionRepository
from riff.db import connection, migrate
from riff.evidence import SourceType
from riff.job_collection import JobCollectionRunner, _records_from_response, source_run_lock
from riff.job_source_policy import JobPolicyError, load_policy
from riff.job_url_intake import JobUrlIntakeRunner


ROOT = Path(__file__).parent
POLICY = ROOT.parent / "config" / "job_sources.json"


def test_job_policy_is_versioned_bounded_and_requires_user_url_mode():
    policy = load_policy(POLICY)
    assert policy.schema_version == 2
    assert {source.source_kind for source in policy.sources} == {"API", "USER_URL"}
    assert policy.source("jobs-permitted-api").enabled is False
    assert policy.source("jobs-user-url").bounds["max_requests"] == 1


def test_job_policy_rejects_enabled_source_without_review():
    payload = json.loads(POLICY.read_text())
    payload["sources"][0]["enabled"] = True
    with pytest.raises(JobPolicyError, match="terms review"):
        load_policy(payload)


def test_json_ld_listing_decomposes_required_fields_and_unknowns():
    policy = load_policy(POLICY)
    source = policy.source("jobs-user-url")
    fetcher = FixtureJobFetcher()
    response = fetcher.fetch("https://jobs.example/listings/url-1", source)
    record = decompose_listing(response.body, final_url=response.final_url, fetched_at=response.fetched_at)
    assert record["provider_posting_id"] == "url-1"
    assert record["role_title"] == "Platform Engineer"
    assert record["company_name"] == "Acme Systems"
    assert record["location"] == "Remote"
    assert record["seniority"] is None
    assert record["metadata"]["parser_version"] == "jobposting-jsonld-v1"


def test_html_fallback_is_bounded_and_records_parser_version():
    policy = load_policy(POLICY)
    source = policy.source("jobs-user-url")
    body = (ROOT / "fixtures" / "jobs" / "url" / "html-fallback.html").read_bytes()
    record = decompose_listing(body, final_url="https://jobs.example/listings/fallback", fetched_at=FixtureJobFetcher().fetch("https://jobs.example/listings/fallback", source).fetched_at)
    assert record["role_title"] == "Software Engineer"
    assert record["metadata"]["parser_version"] == "job-html-fallback-v1"


def test_url_validation_rejects_unsafe_targets_before_fetch():
    source = load_policy(POLICY).source("jobs-user-url")
    with pytest.raises(JobPolicyError, match=r"HTTP\(S\)"):
        validate_target_url("file:///etc/passwd", source, resolve=False)
    with pytest.raises(JobPolicyError, match="allowlist"):
        validate_target_url("https://evil.example/jobs/1", source, resolve=False)
    with pytest.raises(JobPolicyError, match="credentials"):
        validate_target_url("https://user:pass@jobs.example/jobs/1", source, resolve=False)
    with pytest.raises(JobPolicyError, match="non-public"):
        validate_target_url("http://127.0.0.1/jobs/1", replace(source, allowlist=("127.0.0.1",)), resolve=False)


def test_url_intake_dry_run_uses_same_fixture_fetch_boundary():
    policy = load_policy(POLICY)
    result = JobUrlIntakeRunner(
        IngestionRepository("postgresql://unused/unused"),
        EvidenceRepository("postgresql://unused/unused"),
        policy,
        FixtureJobFetcher(),
    ).run("https://jobs.example/listings/url-1", source_id="jobs-user-url", dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert result["posting"]["provider_posting_id"] == "url-1"


def test_collection_response_rejects_malformed_items_without_cursor_advance():
    source = load_policy(POLICY).source("jobs-permitted-api")
    from riff.job_fetch import JobPermanentError

    with pytest.raises(JobPermanentError, match="malformed item"):
        _records_from_response(b'{"schema_version": 1, "postings": [null]}', "https://jobs.example/api/listings", __import__("datetime").datetime.now(), source)


def test_same_source_run_lock_rejects_overlap():
    with source_run_lock("lock-test"):
        with pytest.raises(JobPolicyError, match="already holds"):
            with source_run_lock("lock-test"):
                pass


@pytest.fixture()
def postgres_repositories():
    database_url = __import__("os").environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    ingestion = IngestionRepository(database_url)
    evidence = EvidenceRepository(database_url)
    return database_url, ingestion, evidence


@pytest.mark.postgres
def test_url_intake_persists_raw_evidence_and_decomposition(postgres_repositories):
    database_url, ingestion, evidence = postgres_repositories
    source = evidence.create_source(SourceType.JOBS, "url-fixture", source_id="jobs-user-url")
    ingestion.configure_source(source.source_id, "https://jobs.example/listings/url-1", cursor_kind="jobs:url")
    result = JobUrlIntakeRunner(
        ingestion, evidence, load_policy(POLICY), FixtureJobFetcher()
    ).run("https://jobs.example/listings/url-1", source_id="jobs-user-url")
    assert result["status"] == "SUCCEEDED"
    evidence_id = result["synthesis_receipt"]["evidence_ids"][0]
    with connection(database_url) as conn:
        row = conn.execute("SELECT role_title, seniority, metadata->>'parser_version' FROM job_postings WHERE evidence_id = %s", (evidence_id,)).fetchone()
        raw = conn.execute("SELECT raw_content FROM evidence_versions WHERE evidence_id = %s", (evidence_id,)).fetchone()
    assert tuple(value.decode() if isinstance(value, bytes) else value for value in row) == ("Platform Engineer", None, "jobposting-jsonld-v1")
    assert "JobPosting" in (raw[0].decode() if isinstance(raw[0], bytes) else raw[0])
