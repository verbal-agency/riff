import os
from dataclasses import replace

import pytest

from riff.adapter import RiffToolAdapter, USER_CONFIRMATION_TOKEN
from riff.daily import load_fixture, seed_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository
from riff.dogfood import DogfoodError, load_manifest, mechanical_report, release_report
from riff.explorations import ExplorationRepository
from riff.operations import DailyPipeline
from riff.prds import ProjectRepository


MANIFEST = "tests/fixtures/dogfood/manifest.json"
FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


def test_dogfood_manifest_and_mechanical_report_are_reproducible():
    manifest = load_manifest(MANIFEST)
    assert len(manifest["coverage_weeks"]) == 3
    report = mechanical_report(MANIFEST)
    assert report["mechanical_passed"] is True
    release = release_report(MANIFEST)
    assert release["recommendation"] == "ITERATE"
    assert any(item["status"] == "PENDING_USER" for item in release["criteria"])


def test_dogfood_manifest_rejects_missing_source_fixture(tmp_path):
    payload = load_manifest(MANIFEST)
    payload["sources"][0]["fixture_plan"] = ["/tmp/does-not-exist.json"]
    path = tmp_path / "manifest.json"
    import json

    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DogfoodError, match="missing dogfood fixture"):
        load_manifest(path)


@pytest.fixture()
def dogfood_db():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run PostgreSQL dogfood tests")
    migrate(database_url)
    with connection(database_url) as conn:
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
    return database_url


@pytest.mark.postgres
def test_dogfood_end_to_end_report_and_delivery_trace(dogfood_db):
    database_url = dogfood_db
    report = DailyPipeline(database_url).run(FIXTURE)
    assert report["status"] == "SUCCEEDED" and len(report["stages"]) == 7
    with connection(database_url) as conn:
        riff_id = conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0]
    decisions = DecisionRepository(database_url)
    decisions.record_decision(riff_id, "REJECT", "Not relevant to my current work.")
    assert decisions.resurface_if_changed(riff_id, ["daily-r1"]) is None
    fixture = load_fixture(FIXTURE)
    seed_fixture(database_url, replace(fixture, receipts=fixture.receipts + ({"receipt_id": "daily-r4", "summary": "A newly captured independent signal.", "raw_content": "A newly captured independent signal."},)))
    event = decisions.resurface_if_changed(riff_id, ["daily-r1", "daily-r4"])
    assert event is not None and "daily-r4" in event.explanation
    decisions.record_decision(riff_id, "APPROVE_EXPLORATION", "Now approve exploration after the new evidence.")
    exploration = ExplorationRepository(database_url).create(riff_id)
    exploration = ExplorationRepository(database_url).select_experiment(exploration.exploration_id, exploration.possible_experiments[0].experiment_id)
    projects = ProjectRepository(database_url)
    approval_id = projects.approve_prd(exploration.exploration_id, "Approve this bounded project.")
    project = projects.generate(exploration.exploration_id)
    assert project.approval_id == approval_id and 4 <= project.useful_hours <= 20 and project.exploration_id == exploration.exploration_id
    adapter = RiffToolAdapter(database_url)
    assert adapter.call("get_project", {"project_id": project.project_id})["result"]["project_id"] == project.project_id
