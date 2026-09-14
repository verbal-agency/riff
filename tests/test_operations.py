import os
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from riff.api import create_app
from riff.config import Settings
from riff.daily import load_fixture
from riff.db import connection, migrate
from riff.operations import DailyPipeline, PipelineRepository


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    with connection(value) as conn:
        conn.execute("DELETE FROM pipeline_stages")
        conn.execute("DELETE FROM pipeline_runs")
        conn.execute("DELETE FROM project_versions")
        conn.execute("DELETE FROM project_goals")
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM prd_approvals")
        conn.execute("UPDATE explorations SET selected_experiment_id = NULL")
        conn.execute("DELETE FROM exploration_events")
        conn.execute("DELETE FROM exploration_versions")
        conn.execute("DELETE FROM exploration_experiments")
        conn.execute("DELETE FROM explorations")
        conn.execute("DELETE FROM riff_resurface_events")
        conn.execute("DELETE FROM riff_status_history")
        conn.execute("DELETE FROM riff_decisions")
        conn.execute("DELETE FROM riff_citations")
        conn.execute("DELETE FROM riffs")
        conn.execute("DELETE FROM riff_contexts")
        conn.execute("DELETE FROM daily_riff_runs")
    return value


@pytest.mark.postgres
def test_successful_funnel_is_bounded_and_rerun_is_noop(database_url):
    runner = DailyPipeline(database_url)
    first = runner.run(FIXTURE)
    assert first["status"] == "SUCCEEDED"
    assert [stage["status"] for stage in first["stages"]] == ["COMPLETE"] * 7
    assert first["stages"][-1]["output_count"] <= 3
    second = runner.run(FIXTURE)
    assert second["noop"] is True and second["run_id"] == first["run_id"]
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0] == 1


@pytest.mark.postgres
def test_failure_resumes_without_repeating_completed_stages(database_url):
    runner = DailyPipeline(database_url)
    failed = runner.run(FIXTURE, fail_stage="RIFF")
    assert failed["status"] == "FAILED" and failed["error"] == "injected failure at RIFF"
    resumed = runner.run(FIXTURE, resume=True)
    assert resumed["status"] == "SUCCEEDED"
    stages = {stage["stage_name"]: stage for stage in resumed["stages"]}
    assert stages["COLLECT"]["attempt_count"] == 1
    assert stages["RIFF"]["attempt_count"] == 2
    assert stages["PUBLISH"]["model_calls"] > 0


@pytest.mark.postgres
@pytest.mark.parametrize("stage", ("COLLECT", "RECEIPT", "CAPABILITY", "PROFILE", "SIGNAL", "RIFF", "PUBLISH"))
def test_each_stage_failure_is_resumable(database_url, stage):
    fixture = load_fixture(FIXTURE, run_date=date(2026, 10, 1) + timedelta(days=list(("COLLECT", "RECEIPT", "CAPABILITY", "PROFILE", "SIGNAL", "RIFF", "PUBLISH")).index(stage)), policy_version=f"ops-failure-{stage.lower()}")
    runner = DailyPipeline(database_url)
    failed = runner.run(fixture, fail_stage=stage)
    assert failed["status"] == "FAILED" and failed["current_stage"] == stage
    resumed = runner.run(fixture, resume=True)
    assert resumed["status"] in {"SUCCEEDED", "EMPTY"}
    assert next(item for item in resumed["stages"] if item["stage_name"] == stage)["attempt_count"] == 2


@pytest.mark.postgres
def test_independent_candidate_deep_and_publication_caps(database_url):
    fixture = load_fixture(FIXTURE, run_date=date(2026, 9, 20), policy_version="ops-cap-v1")
    candidates = tuple(replace(item, candidate_id=f"{item.candidate_id}-x{i}", score=item.score - i * 0.001) for i, item in enumerate(fixture.candidates * 4))
    fixture = replace(fixture, candidates=candidates)
    runner = DailyPipeline(database_url, max_candidates=8, max_deep_analyses=2, max_riffs=1)
    report = runner.run(fixture)
    stages = {stage["stage_name"]: stage for stage in report["stages"]}
    assert stages["SIGNAL"]["output_count"] == 8
    assert stages["RIFF"]["input_count"] == 2 and stages["PUBLISH"]["output_count"] <= 1


@pytest.mark.postgres
def test_empty_and_failed_runs_are_distinct_and_policy_forks(database_url):
    fixture = load_fixture(FIXTURE, run_date=date(2026, 9, 21), policy_version="ops-empty-v1")
    empty = replace(fixture, candidates=tuple(replace(item, score=0.1) for item in fixture.candidates))
    report = DailyPipeline(database_url).run(empty)
    assert report["status"] == "EMPTY"
    failed = DailyPipeline(database_url).run(FIXTURE, run_date=date(2026, 9, 22), policy_version="ops-failed-v1", fail_stage="COLLECT")
    assert failed["status"] == "FAILED"
    fork_a = DailyPipeline(database_url).run(FIXTURE, run_date=date(2026, 9, 23), policy_version="ops-policy-a")
    fork_b = DailyPipeline(database_url).run(FIXTURE, run_date=date(2026, 9, 23), policy_version="ops-policy-b")
    assert fork_a["run_id"] != fork_b["run_id"]


@pytest.mark.postgres
def test_claim_concurrency_guard_and_report_api(database_url):
    repository = PipelineRepository(database_url)
    run_date = date(2026, 9, 24)
    run_id, claimed = repository.claim(run_date, "ops-concurrency-v1")
    loser_id, loser_claimed = repository.claim(run_date, "ops-concurrency-v1")
    assert claimed is True and loser_claimed is False and loser_id == run_id
    client = TestClient(create_app(Settings(database_url)))
    response = client.get(f"/operations/{run_id}")
    assert response.status_code == 200 and response.json()["status"] == "RUNNING"
