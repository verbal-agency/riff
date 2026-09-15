import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from riff.adapter import AdapterError, RiffToolAdapter, USER_CONFIRMATION_TOKEN
from riff.api import create_app
from riff.chat_loop import ChatToolLoop, ScriptedModelClient, load_chat_fixture
from riff.config import Settings
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"
CHAT_FIXTURE = "tests/fixtures/chat/tool-loop-v1.json"


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
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
    run_fixture(database_url, load_fixture(FIXTURE))
    with connection(database_url) as conn:
        riffs = [row[0] for row in conn.execute("SELECT riff_id FROM riffs ORDER BY rank").fetchall()]
    return database_url, riffs


@pytest.mark.postgres
def test_scripted_adapter_flow_enforces_approvals_and_survives_restart(graph):
    database_url, riffs = graph
    adapter = RiffToolAdapter(database_url)
    daily = adapter.call("daily_riffs", {"run_date": "2026-09-14"})["result"]
    assert daily["status"] == "COMPLETED" and len(daily["riffs"]) == 3
    investigation = adapter.call("investigate_riff", {"riff_id": riffs[0]})["result"]
    assert investigation["strongest_evidence"] and "profile_slice" not in investigation
    with pytest.raises(AdapterError, match="confirmation"):
        adapter.call("create_exploration", {"riff_id": riffs[0]})
    DecisionRepository(database_url).record_decision(riffs[0], "APPROVE_EXPLORATION", "User approves exploration.")
    exploration = adapter.call("create_exploration", {"riff_id": riffs[0], "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    experiment_id = exploration["possible_experiments"][0]["experiment_id"]
    selected = adapter.call("select_experiment", {"exploration_id": exploration["exploration_id"], "experiment_id": experiment_id, "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    with pytest.raises(AdapterError, match="distinct explicit user"):
        adapter.call("generate_prd", {"exploration_id": selected["exploration_id"]})
    approval = adapter.call("approve_prd", {"exploration_id": selected["exploration_id"], "reason": "Make this a project.", "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    project = adapter.call("generate_prd", {"exploration_id": selected["exploration_id"]})["result"]
    exported = adapter.call("export_project", {"project_id": project["project_id"]})["result"]
    assert approval["approval_id"] == project["approval_id"] and "## Thesis" in exported["markdown"]
    rejected = adapter.call("record_decision", {"riff_id": riffs[1], "decision": "REJECT", "reason": "Not relevant to my current work."})["result"]
    assert rejected["decision"] == "REJECT"
    restarted = RiffToolAdapter(database_url)
    assert restarted.call("get_project", {"project_id": project["project_id"]})["result"]["project_id"] == project["project_id"]


@pytest.mark.postgres
def test_adapter_api_lists_tools_and_preserves_core_api(graph):
    database_url, riffs = graph
    client = TestClient(create_app(Settings(database_url)))
    tools = client.get("/adapter/tools")
    assert tools.status_code == 200 and any(item["name"] == "daily_riffs" for item in tools.json()["tools"])
    missing = client.post("/adapter/tools/create_exploration", json={"riff_id": riffs[0]})
    assert missing.status_code == 409
    daily = client.get("/riffs/daily/2026-09-14")
    assert daily.status_code == 200 and len(daily.json()["riffs"]) == 3


@pytest.mark.postgres
def test_chat_tool_loop_uses_persisted_adapter_state(graph):
    database_url, _ = graph
    fixture = load_chat_fixture(CHAT_FIXTURE)
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "daily")
    model = ScriptedModelClient(scenario["turns"])
    result = ChatToolLoop(model, RiffToolAdapter(database_url)).run(
        scenario["user_message"], system_prompt=fixture["system_prompt"]
    )
    assert result.status == "SUCCEEDED"
    assert result.tool_calls == 1 and result.turns == 2
    assert result.trace[0].name == "daily_riffs"
    assert result.trace[0].result["tool"] == "daily_riffs"
    assert len(result.trace[0].result["result"]["riffs"]) == 3
