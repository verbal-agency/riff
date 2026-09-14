import json
from pathlib import Path

import pytest

from riff.github_discovery import DiscoveryEvaluationError, evaluate_fixture, load_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "github" / "discovery-benchmark-v1.json"


def test_discovery_benchmark_is_deterministic_and_reports_required_metrics():
    fixture = load_fixture(FIXTURE)
    first = evaluate_fixture(fixture)
    second = evaluate_fixture(fixture)

    assert first == second
    assert first["ground_truth_count"] == 5
    assert set(first["strategies"]) == {"curated_scopes", "bounded_topic_search", "graph_expansion"}
    curated = first["strategies"]["curated_scopes"]
    topic = first["strategies"]["bounded_topic_search"]
    graph = first["strategies"]["graph_expansion"]
    assert curated["precision_at_5"] == 1.0
    assert curated["recall_at_5"] == 1.0
    assert topic["precision_at_5"] == 0.8
    assert topic["recall_at_5"] == 0.8
    assert graph["duplicate_or_correlated_rate_at_5"] == 0.6
    assert graph["bot_fork_contamination_at_5"] == 0.6
    for result in first["strategies"].values():
        assert {"request_volume", "retry_count", "pages_examined", "cursor_replays", "cursor_replay_safe"} <= set(result)
    assert first["decision"]["selected_strategy"] == "bounded_topic_search_with_curated_seeds"


def test_fixture_covers_identity_and_contamination_cases():
    fixture = load_fixture(FIXTURE)
    candidates = fixture["candidates"]
    assert any(item["aliases"] for item in candidates)
    assert any(item["is_fork"] for item in candidates)
    assert any(item["is_mirror"] for item in candidates)
    assert any(item["bot_only"] for item in candidates)
    assert any(item["duplicate_of"] for item in candidates)
    assert any(item["stars"] > 50000 and not item["relevant"] for item in candidates)
    assert any(item["artifact_ids"] == ["release:101"] for item in candidates if item["duplicate_of"])


def test_discovery_validation_fails_closed_on_unknown_or_unbounded_candidates():
    fixture = json.loads(FIXTURE.read_text())
    fixture["strategies"][0]["candidate_ids"].append("not-recorded")
    with pytest.raises(DiscoveryEvaluationError, match="unknown or duplicate"):
        evaluate_fixture(fixture)

    fixture = json.loads(FIXTURE.read_text())
    fixture["strategies"][0]["request_volume"] = fixture["bounds"]["max_requests_per_strategy"] + 1
    with pytest.raises(DiscoveryEvaluationError, match="request bound"):
        evaluate_fixture(fixture)
