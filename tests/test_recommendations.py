import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from riff.adapter import AdapterError, RiffToolAdapter, USER_CONFIRMATION_TOKEN
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.recommendations import RecommendationError, RecommendationRepository, build_recommendations
from riff.chat_loop import ChatToolLoop, FixtureToolAdapter, ScriptedModelClient, load_chat_fixture


FIXTURE = Path("tests/fixtures/projects/recommendations.json")
RIFF_FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


def test_matching_is_deterministic_and_preserves_greenfield_alternative():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = build_recommendations(payload["riff"], payload["projects"])
    second = build_recommendations(payload["riff"], payload["projects"])
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert first[0].disposition == "EXTEND_EXISTING"
    assert first[0].project_id == "project-runtime"
    assert first[0].extension_seam == "Add checkpoint replay to the worker"
    assert first[0].project_evidence_ids == ("project-evidence-runtime",)
    assert first[0].signal_evidence_ids == ("signal-evidence-1", "signal-evidence-2")
    assert first[1].disposition == "START_NEW" and first[1].project_id is None
    assert first[0].fit_score > first[1].fit_score


def test_insufficient_evidence_is_not_now_and_has_no_project_target():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    riff = dict(payload["riff"])
    riff["evidence_ids"] = []
    result = build_recommendations(riff, payload["projects"])
    assert len(result) == 1
    assert result[0].disposition == "NOT_NOW"
    assert result[0].project_id is None
    assert any("cited Riff receipt" in item for item in result[0].uncertainty["missing_evidence"])


def test_scripted_chat_surface_returns_bounded_project_match():
    fixture = load_chat_fixture("tests/fixtures/chat/tool-loop-v1.json")
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "project-match")
    result = ChatToolLoop(
        ScriptedModelClient(scenario["turns"]),
        FixtureToolAdapter(fixture["tools"], scenario["adapter_results"]),
    ).run(scenario["user_message"], system_prompt=fixture["system_prompt"])
    assert result.status == "SUCCEEDED"
    assert result.trace[0].name == "match_riff_to_projects"
    assert result.trace[0].result["result"]["recommendations"][0]["disposition"] == "EXTEND_EXISTING"


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM project_recommendations")
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
    run_fixture(database_url, load_fixture(RIFF_FIXTURE))
    with connection(database_url) as conn:
        riff_id = str(conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0])
        source_id = f"g27-recommendation-{uuid.uuid4().hex[:10]}"
        provider_id = f"g27-{uuid.uuid4().hex[:12]}"
        project_id = f"g27-project-{uuid.uuid4().hex[:12]}"
        now = datetime(2026, 9, 15, tzinfo=timezone.utc)
        conn.execute(
            "INSERT INTO sources (source_id, source_type, name, canonical_root, enabled) VALUES (%s, %s, %s, %s, TRUE)",
            (source_id, SourceType.GITHUB.value, "G27 recommendation fixture", f"https://github.com/acme/{provider_id}"),
        )
        conn.execute(
            "INSERT INTO github_repositories (provider_repository_id, source_id, owner_login, name, canonical_url, stars, metadata) VALUES (%s, %s, 'acme', %s, %s, 1, %s)",
            (provider_id, source_id, provider_id, f"https://github.com/acme/{provider_id}", Jsonb({"description": "A durable agent runtime", "visibility": "public"})),
        )
        conn.execute(
            "INSERT INTO github_project_inventory (project_id, provider_repository_id, display_name, purpose, status, visibility, review_status, reviewed_by, reviewed_at) VALUES (%s, %s, 'Agent runtime', 'A durable workflow runtime', 'ACTIVE', 'PUBLIC', 'APPROVED', 'user', %s)",
            (project_id, provider_id, now),
        )
        conn.execute(
            "INSERT INTO github_project_snapshots (snapshot_id, project_id, version, retrieved_at, parser_version, policy_version, input_hash, source_evidence_ids, summary) VALUES (%s, %s, 1, %s, 'fixture', 'fixture', %s, %s, %s)",
            (f"{project_id}-snapshot", project_id, now, "a" * 64, Jsonb(["project-evidence"]), Jsonb({
                "schema_version": 1,
                "project_id": project_id,
                "capabilities": [{"value": "durable-agent-execution"}],
                "technologies": [{"value": "Temporal"}],
                "purpose": {"value": "A durable workflow runtime"},
                "extension_seams": [{"value": "Add checkpoint replay", "status": "OBSERVED", "evidence_ids": ["project-evidence"]}],
                "unknowns": [{"value": "implementation_depth"}],
            })),
        )
    return database_url, riff_id, project_id


@pytest.mark.postgres
def test_persisted_match_and_targeted_exploration_prd(graph):
    database_url, riff_id, project_id = graph
    decisions = DecisionRepository(database_url)
    decisions.record_decision(riff_id, "APPROVE_EXPLORATION", "Approve a targeted extension.")
    repository = RecommendationRepository(database_url)
    result = repository.match_riff(riff_id)
    extension = next(item for item in result["recommendations"] if item["disposition"] == "EXTEND_EXISTING")
    assert extension["project_id"] == project_id
    assert extension["project_snapshot_id"]
    assert extension["signal_evidence_ids"] and extension["project_evidence_ids"]
    assert repository.match_riff(riff_id)["recommendations"][0]["recommendation_id"] == extension["recommendation_id"]
    with pytest.raises(AdapterError, match="confirmation"):
        RiffToolAdapter(database_url).call("propose_extension", {"recommendation_id": extension["recommendation_id"], "confirmation_token": "NO"})
    proposed = RiffToolAdapter(database_url).call("propose_extension", {"recommendation_id": extension["recommendation_id"], "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    assert proposed["exploration"]["target_project_id"] == project_id
    exploration_id = proposed["exploration"]["exploration_id"]
    with connection(database_url) as conn:
        experiment_id = str(conn.execute("SELECT experiment_id FROM exploration_experiments WHERE exploration_id = %s ORDER BY created_at LIMIT 1", (exploration_id,)).fetchone()[0])
    RiffToolAdapter(database_url).call("select_experiment", {"exploration_id": exploration_id, "experiment_id": experiment_id, "confirmation_token": USER_CONFIRMATION_TOKEN})
    RiffToolAdapter(database_url).call("approve_prd", {"exploration_id": exploration_id, "reason": "Approve the targeted PRD.", "confirmation_token": USER_CONFIRMATION_TOKEN})
    project = RiffToolAdapter(database_url).call("generate_prd", {"exploration_id": exploration_id})["result"]
    assert project["prd"]["target_project_id"] == project_id
    assert "Target existing project" in RiffToolAdapter(database_url).call("export_project", {"project_id": project["project_id"]})["result"]["markdown"]


@pytest.mark.postgres
def test_recommendation_override_preserves_original_and_is_confirmation_gated(graph):
    database_url, riff_id, _ = graph
    result = RecommendationRepository(database_url).match_riff(riff_id)
    recommendation_id = result["recommendations"][0]["recommendation_id"]
    adapter = RiffToolAdapter(database_url)
    with pytest.raises(AdapterError, match="confirmation"):
        adapter.call("override_recommendation", {"recommendation_id": recommendation_id, "disposition": "START_NEW", "reason": "Prefer greenfield."})
    overridden = adapter.call("override_recommendation", {"recommendation_id": recommendation_id, "disposition": "START_NEW", "reason": "Prefer greenfield.", "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    assert overridden["disposition"] == "EXTEND_EXISTING"
    assert overridden["effective_disposition"] == "START_NEW"
    assert overridden["status"] == "OVERRIDDEN"
