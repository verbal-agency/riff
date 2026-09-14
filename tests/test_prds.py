import os

import pytest
from fastapi.testclient import TestClient

from riff.api import create_app
from riff.config import Settings
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository
from riff.explorations import DeterministicExplorationGenerator, ExplorationRepository, Experiment, Exploration
from riff.prds import DeterministicPrdGenerator, PrdError, Project, ProjectGoal, ProjectRepository, PRD_SECTIONS, validate_project


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


def _exploration(exploration_id="e-1", capability="durable-agent-execution", artifact="A reproducible demo and measurement."):
    experiment = Experiment(
        f"{exploration_id}-exp-1", exploration_id, "Bounded slice", "Build and measure a small slice.", capability,
        ("Temporal", "LangGraph"), ("understand", "implement", "inspect", "compare", "demonstrate"), 10.0,
        ("One focused session",), artifact, ("Explain the design", "Show the result"),
        {"useful": True, "capability_driven": True, "concrete": True, "discussable": True, "completable": True, "portfolio_capable": True},
    )
    return Exploration(
        exploration_id, "riff-1", "approval-1", "SELECTED", "Durable execution is differentiating.",
        "It makes recovery visible.", "What evidence shows recovery is useful?", (capability,), ("Temporal", "LangGraph"),
        ("Which trade-off matters?",), (experiment,), {"min_hours": 10, "max_hours": 10}, ("Explain recovery",), 1, experiment.experiment_id,
    )


def test_prd_generator_contains_all_section_19_fields_for_distinct_explorations():
    generator = DeterministicPrdGenerator()
    first = generator.generate(_exploration("e-1"))
    second = generator.generate(_exploration("e-2", "agent-observability", "A public demonstrative artifact with measured output."))
    assert set(PRD_SECTIONS) == set(first["prd"])
    assert all(first["prd"][section] for section in PRD_SECTIONS)
    assert first["prd"]["capability_target"] != second["prd"]["capability_target"]
    assert "public demonstrative artifact" in " ".join(second["prd"]["scope"])
    assert len(first["goals"]) == 3
    assert first["goals"][0].dependencies == () and first["goals"][1].dependencies == (first["goals"][0].goal_id,)
    project = Project("p-1", "e-1", "approval-1", "READY", 1, first["useful_hours"], first["prd"], first["goals"])
    validate_project(project)


def test_validator_rejects_vague_acceptance_criteria_and_cycles():
    generated = DeterministicPrdGenerator().generate(_exploration())
    vague_goal = ProjectGoal(generated["goals"][0].goal_id, generated["project_id"], 1, "Vague", "Outcome", ("input",), "deliverable", (), (), ("It works well",), ("test",))
    with pytest.raises(PrdError, match="vague"):
        validate_project(Project(generated["project_id"], "e-1", "a-1", "READY", 1, 10, generated["prd"], (vague_goal,)))
    first, second, third = generated["goals"]
    cyclic = (ProjectGoal(first.goal_id, first.project_id, 1, first.title, first.outcome, first.inputs, first.deliverable, (second.goal_id,), first.non_goals, first.acceptance_criteria, first.verification_evidence), second, third)
    with pytest.raises(PrdError, match="cycle"):
        validate_project(Project(generated["project_id"], "e-1", "a-1", "READY", 1, 10, generated["prd"], cyclic))


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
    run_fixture(database_url, load_fixture(FIXTURE))
    with connection(database_url) as conn:
        riff_id = conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0]
    DecisionRepository(database_url).record_decision(riff_id, "APPROVE_EXPLORATION", "Approve exploration.")
    exploration = ExplorationRepository(database_url).create(riff_id)
    exploration = ExplorationRepository(database_url).select_experiment(exploration.exploration_id, exploration.possible_experiments[0].experiment_id)
    return database_url, exploration.exploration_id


@pytest.mark.postgres
def test_prd_requires_distinct_approval_is_idempotent_and_versions(graph):
    database_url, exploration_id = graph
    repository = ProjectRepository(database_url)
    with pytest.raises(PrdError, match="distinct explicit user"):
        repository.generate(exploration_id)
    approval_id = repository.approve_prd(exploration_id, "Make this selected experiment a project.")
    first = repository.generate(exploration_id)
    second = repository.generate(exploration_id)
    assert first.project_id == second.project_id and first.approval_id == approval_id
    assert 4 <= first.useful_hours <= 20 and len(first.goals) == 3
    assert set(PRD_SECTIONS) == set(first.prd)
    markdown = repository.export_markdown(first.project_id)
    assert markdown == repository.export_markdown(first.project_id)
    assert f"{exploration_id}" in markdown and approval_id in markdown
    regenerated = repository.regenerate(first.project_id, reason="Clarify the comparison.")
    assert regenerated.version == 2 and regenerated.approval_id == approval_id


@pytest.mark.postgres
def test_prd_api_approval_generation_and_export(graph):
    database_url, exploration_id = graph
    client = TestClient(create_app(Settings(database_url)))
    blocked = client.post(f"/explorations/{exploration_id}/prd", json={})
    assert blocked.status_code == 409
    approved = client.post(f"/explorations/{exploration_id}/prd-approvals", json={"reason": "Approve project generation."})
    assert approved.status_code == 200
    generated = client.post(f"/explorations/{exploration_id}/prd", json={})
    assert generated.status_code == 200
    project_id = generated.json()["project_id"]
    fetched = client.get(f"/projects/{project_id}")
    exported = client.get(f"/projects/{project_id}/markdown")
    assert fetched.status_code == 200 and len(fetched.json()["goals"]) == 3
    assert exported.status_code == 200 and all(f"## {section.replace('_', ' ').title()}" in exported.json()["markdown"] for section in PRD_SECTIONS)
