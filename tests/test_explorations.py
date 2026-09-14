import os

import pytest

from riff.api import create_app
from riff.config import Settings
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository, Investigation
from riff.explorations import DeterministicExplorationGenerator, ExplorationError, ExplorationRepository
from fastapi.testclient import TestClient


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


def _investigation(user_relevance="SIGNALING_GAP"):
    return Investigation(
        riff_id="r-1",
        status="EXPLORING",
        riff={
            "hypothesis": "Durable execution is a differentiating capability",
            "observation": "Independent evidence converges",
            "why_it_matters": "It turns failure handling into a visible engineering skill.",
            "underlying_capability": "durable-agent-execution",
            "associated_technologies": ["Temporal", "LangGraph"],
            "user_relevance": user_relevance,
        },
        supporting_evidence=(),
        counterevidence=(),
        profile_slice=(),
        decision_history=(),
        source_breakdown={},
    )


def test_generator_produces_schema_complete_bounded_options():
    result = DeterministicExplorationGenerator().generate(_investigation())
    assert result["thesis"] and result["why_it_matters"] and result["what_i_want_to_understand"]
    assert result["capability_targets"] and result["technology_targets"] and result["open_questions"]
    assert result["evidence_of_competence"] and len(result["possible_experiments"]) >= 3
    assert all(4 <= option.effort_hours <= 20 for option in result["possible_experiments"])
    assert len({option.title for option in result["possible_experiments"]}) == 3


def test_signaling_gap_prefers_public_artifact_and_reduces_overlarge_project():
    result = DeterministicExplorationGenerator().generate(_investigation(), overlarge=True)
    first = result["possible_experiments"][0]
    assert "public" in first.title.lower() and "public" in first.artifact_or_measurement.lower()
    assert first.selection_rules["reduced_from_hours"] == 40
    assert first.effort_hours <= 20


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM project_versions")
        conn.execute("DELETE FROM project_goals")
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM prd_approvals")
        conn.execute("DELETE FROM exploration_events")
        conn.execute("DELETE FROM exploration_versions")
        conn.execute("UPDATE explorations SET selected_experiment_id = NULL")
        conn.execute("DELETE FROM exploration_experiments")
        conn.execute("DELETE FROM explorations")
        conn.execute("DELETE FROM riff_resurface_events")
        conn.execute("DELETE FROM riff_status_history")
        conn.execute("DELETE FROM riff_decisions")
        conn.execute("DELETE FROM riff_citations")
        conn.execute("DELETE FROM riffs")
        conn.execute("DELETE FROM riff_contexts")
        conn.execute("DELETE FROM daily_riff_runs")
    result = run_fixture(database_url, load_fixture(FIXTURE))
    with connection(database_url) as conn:
        riff_id = conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0]
    return database_url, riff_id, result["run_id"]


@pytest.mark.postgres
def test_creation_requires_approval_and_is_idempotent(graph):
    database_url, riff_id, _ = graph
    repository = ExplorationRepository(database_url)
    with pytest.raises(ExplorationError, match="explicit user"):
        repository.create(riff_id)
    approval = DecisionRepository(database_url).record_decision(riff_id, "APPROVE_EXPLORATION", "I approve exploration.")
    first = repository.create(riff_id)
    second = repository.create(riff_id)
    assert first.exploration_id == second.exploration_id
    assert first.approval_decision_id == approval.decision_id
    assert len(first.possible_experiments) == 3
    assert all(set(("understand", "implement", "inspect", "compare", "demonstrate")).issubset(set(e.learning_steps)) for e in first.possible_experiments)
    assert first.capability_targets and first.technology_targets and first.evidence_of_competence


@pytest.mark.postgres
def test_refinement_preserves_original_and_selection_stops_before_prd(graph):
    database_url, riff_id, _ = graph
    decisions = DecisionRepository(database_url)
    decisions.record_decision(riff_id, "APPROVE_EXPLORATION", "Approve a bounded investigation.")
    repository = ExplorationRepository(database_url)
    exploration = repository.create(riff_id)
    refined = repository.refine(exploration.exploration_id, exploration.possible_experiments[0].experiment_id, "Too broad; make the public artifact smaller.")
    original = next(e for e in refined.possible_experiments if e.experiment_id == exploration.possible_experiments[0].experiment_id)
    replacement = next(e for e in refined.possible_experiments if e.experiment_id != original.experiment_id and e.title.startswith("Refined:"))
    assert original.status == "REJECTED" and replacement.status == "PROPOSED"
    assert any(event["reason"] == "Too broad; make the public artifact smaller." for event in refined.history)
    selected = repository.select_experiment(refined.exploration_id, replacement.experiment_id)
    assert selected.status == "SELECTED" and selected.selected_experiment_id == replacement.experiment_id
    with connection(database_url) as conn:
        assert conn.execute("SELECT to_regclass('public.prds')").fetchone()[0] is None


@pytest.mark.postgres
def test_exploration_api_operations(graph):
    database_url, riff_id, _ = graph
    DecisionRepository(database_url).record_decision(riff_id, "APPROVE_EXPLORATION", "Approve exploration from the user.")
    client = TestClient(create_app(Settings(database_url)))
    created = client.post(f"/riffs/{riff_id}/explorations", json={})
    assert created.status_code == 200
    exploration_id = created.json()["exploration_id"]
    fetched = client.get(f"/explorations/{exploration_id}")
    assert fetched.status_code == 200 and len(fetched.json()["possible_experiments"]) == 3
