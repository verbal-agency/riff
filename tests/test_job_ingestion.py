import json
import os
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.ingestion_repository import IngestionRepository, RunStatus
from riff.job_ingestion import JobImportError, JobIngestionRunner, load_job_fixture


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "jobs"


@pytest.fixture()
def repositories():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    ingestion = IngestionRepository(database_url)
    evidence = EvidenceRepository(database_url)
    source = evidence.create_source(SourceType.JOBS, "fixture-jobs")
    ingestion.configure_source(source.source_id, "https://jobs.example/import", cursor_kind="jobs:import")
    return database_url, ingestion, evidence, source


def _run(ingestion, evidence, source, filename, **kwargs):
    return JobIngestionRunner(ingestion, evidence, **kwargs).run_file(
        FIXTURE_DIR / filename,
        source_ids=[source.source_id],
    )


@pytest.mark.postgres
def test_job_three_passes(repositories):
    _, ingestion, evidence, source = repositories
    first = _run(ingestion, evidence, source, "initial.json")
    unchanged = _run(ingestion, evidence, source, "initial.json")
    incremented = _run(ingestion, evidence, source, "incremented.json")

    assert (first.status, first.stored) == (RunStatus.SUCCEEDED, 3)
    assert (unchanged.status, unchanged.stored, unchanged.duplicates) == (RunStatus.SUCCEEDED, 0, 3)
    assert (incremented.status, incremented.stored, incremented.duplicates) == (RunStatus.SUCCEEDED, 2, 2)
    assert evidence.source_item_count(source.source_id) == 4


@pytest.mark.postgres
def test_repost_retrieval_and_changed_version(repositories):
    database_url, ingestion, evidence, source = repositories
    _run(ingestion, evidence, source, "initial.json")
    _run(ingestion, evidence, source, "incremented.json")
    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT si.native_id, count(DISTINCT e.evidence_id), count(DISTINCT r.retrieval_id) "
            "FROM source_items si JOIN evidence_versions e ON e.source_item_id = si.source_item_id "
            "JOIN retrievals r ON r.evidence_id = e.evidence_id "
            "WHERE si.source_id = %s GROUP BY si.native_id ORDER BY si.native_id",
            (source.source_id,),
        ).fetchall()
    by_id = {item[0].decode() if isinstance(item[0], bytes) else item[0]: item[1:] for item in rows}
    assert by_id["job-1"] == (1, 2)  # exact repost, one version and two retrievals
    assert by_id["job-2"] == (2, 2)  # changed body, two versions and two retrievals


@pytest.mark.postgres
def test_one_employer_burst_correlates_identity(repositories):
    database_url, ingestion, evidence, source = repositories
    summary = _run(ingestion, evidence, source, "burst.json")
    assert summary.stored == 20
    with connection(database_url) as conn:
        employer_count = conn.execute(
            "SELECT count(DISTINCT employer_id) FROM job_postings WHERE source_id = %s",
            (source.source_id,),
        ).fetchone()[0]
        posting_count = conn.execute(
            "SELECT count(*) FROM job_postings WHERE source_id = %s",
            (source.source_id,),
        ).fetchone()[0]
    assert (posting_count, employer_count) == (20, 1)


@pytest.mark.postgres
def test_ambiguous_employer_alias_is_reversible(repositories):
    database_url, ingestion, evidence, source = repositories
    _run(ingestion, evidence, source, "ambiguous.json")
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT e.identity_state, a.status, a.alias FROM job_employers e "
            "JOIN job_employer_aliases a ON a.employer_id = e.employer_id "
            "WHERE e.source_id = %s",
            (source.source_id,),
        ).fetchone()
    assert tuple(item.decode() if isinstance(item, bytes) else item for item in row) == (
        "AMBIGUOUS",
        "CANDIDATE",
        "Acme Incorporated",
    )


@pytest.mark.postgres
def test_missing_fields_remain_unknown_and_expired_evidence_survives(repositories):
    database_url, ingestion, evidence, source = repositories
    _run(ingestion, evidence, source, "missing-fields.json")
    _run(ingestion, evidence, source, "expired.json")
    with connection(database_url) as conn:
        missing = conn.execute(
            "SELECT seniority, compensation, published_at FROM job_postings WHERE source_id = %s AND provider_posting_id = 'missing-1'",
            (source.source_id,),
        ).fetchone()
        expired = conn.execute(
            "SELECT expired FROM job_postings WHERE source_id = %s AND provider_posting_id = 'expired-1'",
            (source.source_id,),
        ).fetchone()
    assert missing == (None, None, None)
    assert expired[0] is True


@pytest.mark.postgres
def test_jobs_are_searchable_by_employer_role_date(repositories):
    _, ingestion, evidence, source = repositories
    _run(ingestion, evidence, source, "initial.json")
    found = evidence.search(source_id=source.source_id, job_employer_name="Acme", job_role_text="Platform")
    assert len(found) == 1
    assert found[0].native_id == "job-2"


@pytest.mark.postgres
def test_malformed_record_is_inspectable_without_rolling_back_valid_rows(repositories):
    database_url, ingestion, evidence, source = repositories
    payload = json.loads((FIXTURE_DIR / "initial.json").read_text())
    payload["postings"].append(json.loads((FIXTURE_DIR / "malformed.json").read_text())["postings"][0])
    path = FIXTURE_DIR / "_temporary_malformed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        summary = _run(ingestion, evidence, source, path.name)
    finally:
        path.unlink()
    assert (summary.status, summary.stored, summary.failed_permanent) == (RunStatus.PARTIAL, 3, 1)
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM job_postings WHERE source_id = %s", (source.source_id,)).fetchone()[0] == 3


def test_import_fixture_is_offline_and_schema_valid(tmp_path):
    observed_at, postings = load_job_fixture(FIXTURE_DIR / "initial.json")
    assert observed_at.tzinfo is not None
    assert len(postings) == 3
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{\"schema_version\": 2}", encoding="utf-8")
    with pytest.raises(JobImportError):
        load_job_fixture(invalid)
