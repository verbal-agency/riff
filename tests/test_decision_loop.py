import os
from dataclasses import replace
from datetime import date

import pytest

from riff.daily import load_fixture, run_fixture, seed_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionError, DecisionRepository
from riff.api import create_app
from riff.config import Settings
from fastapi.testclient import TestClient


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


@pytest.fixture()
def graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM riff_resurface_events")
        conn.execute("DELETE FROM riff_status_history")
        conn.execute("DELETE FROM riff_decisions")
        conn.execute("DELETE FROM riff_citations")
        conn.execute("DELETE FROM riffs")
        conn.execute("DELETE FROM riff_contexts")
        conn.execute("DELETE FROM daily_riff_runs")
    fixture = load_fixture(FIXTURE)
    result = run_fixture(database_url, fixture)
    return database_url, result["run_id"]


def _first_riff(database_url):
    with connection(database_url) as conn:
        return conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0]


@pytest.mark.postgres
def test_rejection_stores_reason_and_framework_implications(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    repository = DecisionRepository(database_url)
    decision = repository.record_decision(riff_id, "REJECT", "Too framework-specific; the underlying capability matters.")
    assert decision.reason == "Too framework-specific; the underlying capability matters."
    assert repository.effective_implications(riff_id)["framework_adoption_penalty"] == -1
    assert repository.effective_implications(riff_id)["underlying_capability_interest"] == 1
    assert repository.investigation(riff_id).status == "REJECTED"


@pytest.mark.postgres
def test_professional_knowledge_requires_confirmation(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    repository = DecisionRepository(database_url)
    repository.record_decision(riff_id, "WATCH", "I already understand this professionally.")
    before = repository.effective_implications(riff_id)
    assert before["profile_update_proposed"] and before["profile_update_confirmed"] is False and before["novelty_adjustment"] == 0
    repository.record_decision(riff_id, "CONFIRM_PROFILE_UPDATE", "Confirm the proposed professional profile update.")
    after = repository.effective_implications(riff_id)
    assert after["profile_update_confirmed"] and after["novelty_adjustment"] < 0


@pytest.mark.postgres
def test_only_user_can_approve_exploration_and_invalid_transition_is_safe(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    repository = DecisionRepository(database_url)
    with pytest.raises(DecisionError, match="explicit user"):
        repository.record_decision(riff_id, "APPROVE_EXPLORATION", "go", actor="model", actor_kind="MODEL")
    repository.record_decision(riff_id, "WATCH", "watch this")
    repository.record_decision(riff_id, "APPROVE_EXPLORATION", "I approve exploration")
    assert repository.investigation(riff_id).status == "EXPLORING"
    with pytest.raises(DecisionError, match="illegal transition"):
        repository.record_decision(riff_id, "REJECT", "too late")
    assert repository.investigation(riff_id).status == "EXPLORING"


@pytest.mark.postgres
def test_unchanged_rejection_does_not_resurface_but_material_change_does(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    repository = DecisionRepository(database_url)
    repository.record_decision(riff_id, "REJECT", "Vendor churn around an existing capability.")
    assert repository.resurface_if_changed(riff_id, ["daily-r1"]) is None
    fixture = load_fixture(FIXTURE)
    changed = replace(fixture, receipts=fixture.receipts + ({"receipt_id": "daily-r4", "summary": "A new independent implementation appears.", "raw_content": "A new independent implementation appears."},))
    seed_fixture(database_url, changed)
    event = repository.resurface_if_changed(riff_id, ["daily-r1", "daily-r4"])
    assert event is not None and "Vendor churn" in event.explanation and "daily-r4" in event.explanation
    assert repository.investigation(riff_id).status == "WATCHING"


@pytest.mark.postgres
def test_investigation_returns_only_linked_evidence(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    investigation = DecisionRepository(database_url).investigation(riff_id)
    assert len(investigation.supporting_evidence) == 1
    assert investigation.supporting_evidence[0]["raw_content"]


@pytest.mark.postgres
def test_decision_and_investigation_api_operations(graph):
    database_url, _ = graph
    riff_id = _first_riff(database_url)
    client = TestClient(create_app(Settings(database_url)))
    response = client.post(f"/riffs/{riff_id}/decisions", json={"decision": "WATCH", "reason": "Review again next week."})
    assert response.status_code == 200 and response.json()["decision"] == "WATCH"
    investigation = client.get(f"/riffs/{riff_id}/investigation")
    assert investigation.status_code == 200 and investigation.json()["status"] == "WATCHING"
