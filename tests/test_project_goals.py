import json
import os
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.project_goals import extract_goals, rank_goal_guidance
from riff.project_goals import ProjectGoalRepository


FIXTURE = Path(__file__).parent / "fixtures" / "github" / "goals" / "project-goals-v1.json"


def test_extracts_explicit_goals_with_provenance_and_separates_files():
    payload = json.loads(FIXTURE.read_text())
    goals = extract_goals(payload["project"], payload["artifacts"], snapshot_id="snapshot-1")
    assert len(goals) == 3
    assert {goal["source_surface"] for goal in goals} == {"README_CHANGE", "ISSUE"}
    assert all(goal["source_evidence_ids"] for goal in goals)
    assert all(goal["parser_version"] == "github-project-goals-v1" for goal in goals)
    assert all(goal["status"] in {"ACTIVE", "UNKNOWN"} for goal in goals)
    assert not any(goal["title"] == "README.md" for goal in goals)


def test_goal_guidance_is_bounded_and_surfaces_synthetic_uncertainty():
    payload = json.loads(FIXTURE.read_text())
    goal = extract_goals(payload["project"], payload["artifacts"], snapshot_id="snapshot-1")[0]
    goal["synthetic"] = True
    result = rank_goal_guidance(goal, delta={"status": "NEW", "source_evidence_ids": ["riff-evidence"], "claims": {}, "uncertainty": []}, project=payload["project"], profile={"classification": "UNKNOWN"}, opportunity={"kind": "demo"})
    assert len(result["actions"]) <= 3
    assert result["actions"][0]["action_type"] == "INVESTIGATE_GAP"
    assert "goal_or_evidence_is_synthetic" in result["uncertainty"]
    assert result["context"] == {"profile_used": True, "decision_count": 0, "opportunity_used": True}


@pytest.mark.postgres
def test_goal_projection_replay_is_idempotent_and_changed_wording_links_history():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        row = conn.execute("SELECT i.project_id,s.snapshot_id FROM github_project_inventory i JOIN github_project_snapshots s USING (project_id) ORDER BY s.version DESC LIMIT 1").fetchone()
    if row is None:
        pytest.skip("requires one selected project with a snapshot")
    project_id, snapshot_id = row
    project = {"project_id": project_id}
    first = extract_goals(project, [{"evidence_id": "g37-test-evidence", "artifact_type": "README_CHANGE", "canonical_url": "https://fixture.test/g37", "content": "Goal G37 test projection (active)"}], snapshot_id=snapshot_id)
    repo = ProjectGoalRepository(database_url)
    inserted = repo.persist(project, snapshot_id, first)
    repeated = repo.persist(project, snapshot_id, first)
    assert inserted[0]["goal_version_id"] == repeated[0]["goal_version_id"]
    changed = extract_goals(project, [{"evidence_id": "g37-test-evidence", "artifact_type": "README_CHANGE", "canonical_url": "https://fixture.test/g37", "content": "Goal G37 test projection revised (active)"}], snapshot_id=snapshot_id)
    revised = repo.persist(project, snapshot_id, changed)
    assert revised[0]["prior_goal_version_id"] == inserted[0]["goal_version_id"]
    with connection(database_url) as conn:
        conn.execute("DELETE FROM github_project_goal_events WHERE goal_version_id = ANY(%s)", ([inserted[0]["goal_version_id"], revised[0]["goal_version_id"]],))
        conn.execute("DELETE FROM github_project_goal_versions WHERE goal_version_id = ANY(%s)", ([inserted[0]["goal_version_id"], revised[0]["goal_version_id"]],))
