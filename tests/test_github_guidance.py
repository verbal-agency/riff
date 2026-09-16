import json
import os
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.github_guidance import GitHubGuidanceRepository, project_delta, rank_guidance


FIXTURE = Path(__file__).parent / "fixtures" / "github" / "guidance" / "project-delta-v1.json"


def test_project_delta_is_deterministic_and_cites_changed_evidence():
    payload = json.loads(FIXTURE.read_text())
    result = project_delta(payload["previous_summary"], payload["current_summary"], current_snapshot_id="snapshot-new", previous_snapshot_id="snapshot-old")
    assert result["status"] == "CHANGED"
    assert result["input_fingerprint"] == project_delta(payload["previous_summary"], payload["current_summary"], current_snapshot_id="snapshot-new", previous_snapshot_id="snapshot-old")["input_fingerprint"]
    assert "evidence-new" in result["source_evidence_ids"]
    assert any(item["value"] == "Replay after worker restart" for item in result["claims"]["added"])


def test_guidance_ranks_extension_and_gap_without_claiming_proficiency():
    payload = json.loads(FIXTURE.read_text())
    delta = project_delta(payload["previous_summary"], payload["current_summary"], current_snapshot_id="snapshot-new", previous_snapshot_id="snapshot-old")
    guidance = rank_guidance(delta, project=payload["project"])
    assert len(guidance["actions"]) <= 3
    assert guidance["actions"][0]["action_type"] in {"EXTEND_PROJECT", "INVESTIGATE_GAP"}
    assert "proficiency" not in json.dumps(guidance).lower()


def test_guidance_exposes_supplied_context_without_persisting_raw_text():
    payload = json.loads(FIXTURE.read_text())
    delta = project_delta(payload["previous_summary"], payload["current_summary"], current_snapshot_id="snapshot-new", previous_snapshot_id="snapshot-old")
    guidance = rank_guidance(
        delta,
        project=payload["project"],
        profile={"capability": "unknown"},
        decisions=[{"decision": "DEFERRED", "reason": "not now"}],
        opportunity={"platform": "bounded"},
    )
    assert guidance["context"] == {"profile_used": True, "decision_count": 1, "opportunity_used": True}
    assert "not now" not in json.dumps(guidance)


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    return value


@pytest.mark.postgres
def test_guidance_replay_is_idempotent_and_feedback_is_append_only(database_url):
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT p.project_id FROM github_project_inventory p "
            "JOIN github_project_snapshots s USING (project_id) "
            "GROUP BY p.project_id HAVING count(s.snapshot_id) >= 2 "
            "ORDER BY p.project_id LIMIT 1"
        ).fetchone()
    if row is None:
        pytest.skip("requires a selected project with two persisted snapshots")

    repository = GitHubGuidanceRepository(database_url)
    first = repository.analyze(row[0])
    repeat = repository.analyze(row[0])
    assert repeat["delta"]["delta_id"] == first["delta"]["delta_id"]
    assert repeat["guidance"]["guidance_id"] == first["guidance"]["guidance_id"]
    assert len(first["guidance"]["actions"]) <= 3

    feedback = repository.feedback(
        first["guidance"]["guidance_id"],
        "CORRECTED",
        "Keep the evidence gap explicit.",
        correction={"action_type": "INVESTIGATE_GAP"},
    )
    audit = repository.audit(row[0])
    assert feedback["feedback_id"]
    assert audit["feedback"][0]["decision"] == "CORRECTED"
    assert audit["memory_layers"] == [
        "evidence_ledger",
        "project_understanding",
        "user_decision_memory",
        "guidance_memory",
        "conversation_context",
    ]
