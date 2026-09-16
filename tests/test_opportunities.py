import json
import os
import uuid
from pathlib import Path

import pytest

from riff.db import connection, migrate
from riff.chat_loop import ChatToolLoop, FixtureToolAdapter, ScriptedModelClient, load_chat_fixture
from riff.opportunities import OpportunityRepository
from riff.opportunities import OpportunityError, build_execution_candidates, compare_candidates, extract_context, riff_candidate


FIXTURE = Path("tests/fixtures/opportunities/perplexity-computer.json")


def test_perplexity_fixture_extracts_context_without_universalizing_platform():
    context = extract_context("https://example.test/opportunities/perplexity-computer", json.loads(FIXTURE.read_text()))
    assert "Perplexity Computer" in context.platforms
    assert "human approval before consequential actions" in context.approvals
    assert context.unknowns
    other = extract_context("https://example.test/opportunities/other", {"title": "Other role", "description": "Build an API workflow."})
    assert "Perplexity Computer" not in other.platforms
    with pytest.raises(OpportunityError, match=r"HTTP\(S\)"):
        extract_context("not-a-url", {})
    with pytest.raises(OpportunityError, match="configured bound"):
        extract_context("https://example.test/large", {"description": "x" * 20_001})


def test_candidates_are_diverse_and_riffing_preserves_lineage():
    context = extract_context("https://example.test/opportunities/perplexity-computer", json.loads(FIXTURE.read_text()))
    candidates = build_execution_candidates(context, project_seam="Extend Riff's workflow runtime")
    assert len(candidates) >= 3
    assert len({item.boundary for item in candidates}) >= 3
    variant = riff_candidate(candidates[0], "NARROW")
    assert variant.parent_candidate_id == candidates[0].candidate_id
    assert variant.operation == "NARROW"
    second_variant = riff_candidate(variant, "CONSTRAIN", constraint="one workflow only")
    assert second_variant.parent_candidate_id == variant.candidate_id
    comparison = compare_candidates([*candidates, variant, second_variant])
    assert comparison["candidates"]
    assert comparison["policy_version"]


def test_scripted_conversation_can_inspect_riff_compare_without_approval_mutation():
    fixture = load_chat_fixture("tests/fixtures/chat/tool-loop-v1.json")
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "opportunity-riff")
    result = ChatToolLoop(
        ScriptedModelClient(scenario["turns"]),
        FixtureToolAdapter(fixture["tools"], scenario["adapter_results"]),
    ).run(scenario["user_message"], system_prompt=fixture["system_prompt"])
    assert result.status == "SUCCEEDED"
    assert [item.name for item in result.trace] == [
        "inspect_opportunity", "list_execution_candidates", "riff_execution_candidate", "compare_execution_candidates"
    ]


@pytest.mark.postgres
def test_context_candidates_and_selection_persist_without_creating_prd():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    source_url = f"https://example.test/opportunities/{uuid.uuid4().hex}"
    context = extract_context(source_url, json.loads(FIXTURE.read_text()))
    repository = OpportunityRepository(database_url)
    repository.persist_context(context)
    candidates = repository.persist_candidates(build_execution_candidates(context, project_seam="Extend Riff runtime"))
    variant = riff_candidate(candidates[0], "CONSTRAIN", constraint="one workflow and no private data")
    repository.persist_candidates([variant])
    selected = repository.select(context.opportunity_id, variant.candidate_id, "The constrained failure probe is the most distinctive.")
    assert selected["status"] == "SELECTED"
    assert selected["next_approval"] == "APPROVE_EXPLORATION"
    assert repository.get_context(context.opportunity_id).platforms == ("Perplexity Computer",)
    with connection(database_url) as conn:
        conn.execute("DELETE FROM opportunities WHERE opportunity_id = %s", (context.opportunity_id,))
