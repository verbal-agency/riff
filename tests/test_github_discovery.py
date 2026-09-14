import json
from pathlib import Path

import pytest

from riff.github_discovery import (
    DiscoveryPolicyError,
    DiscoveryEvaluationError,
    FixtureDiscoveryFetcher,
    approve_candidates,
    discover,
    evaluate_fixture,
    load_fixture,
    load_policy,
    promote_candidates,
    write_queue,
)
from riff.github_ingestion import GitHubResponse


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


POLICY = {
    "schema_version": 1,
    "policy_id": "test-policy",
    "query_terms": ["durable execution", "agent orchestration"],
    "seed_source_ids": ["github-langgraph"],
    "max_pages_per_query": 2,
    "max_candidates_per_query": 6,
    "max_requests": 10,
    "max_contributor_expansion": 0,
    "retry_limit": 1,
    "stop_rules": {"root_concentration_threshold": 0.25},
    "review_required": True,
    "enabled": False,
}


def test_bounded_discovery_builds_review_queue_from_recorded_searches():
    fixture = Path(__file__).parent / "fixtures" / "github" / "discovery" / "search-responses-v1.json"
    result = discover(load_policy(POLICY), FixtureDiscoveryFetcher(fixture), fixture_id="g20-search-responses-v1")

    assert result["request_count"] == 4
    assert result["pages_examined"] == 4
    candidates = {item["candidate_id"]: item for item in result["candidates"]}
    assert candidates["repo:5252"]["filter_reasons"] == ["FORK", "ROOT_CONCENTRATION"]
    assert "BOT" in candidates["repo:7002"]["filter_reasons"]
    assert candidates["repo:7001"]["filter_reasons"] == ["POPULARITY_ONLY"]
    assert all(item["source_scope"]["enabled"] is False for item in candidates.values())


def test_discovery_policy_bounds_fail_closed():
    invalid = dict(POLICY, query_terms=["one", "two", "three", "four"])
    with pytest.raises(DiscoveryPolicyError, match="one to three"):
        load_policy(invalid)


def test_seeded_discovery_preserves_input_kind_attribution_and_correlation():
    fixture = Path(__file__).parent / "fixtures" / "github" / "discovery" / "seed-responses-v1.json"
    policy = dict(
        POLICY,
        query_terms=["durable execution"],
        capability_terms=["durable execution"],
        repository_seeds=["acme/riff-runtime"],
        engineer_seeds=["alice"],
        organization_seeds=["acme"],
        max_queries=4,
        max_pages_per_query=2,
        max_requests=8,
    )
    result = discover(load_policy(policy), FixtureDiscoveryFetcher(fixture), fixture_id="g25-seed-inputs-v1")
    replay = discover(load_policy(policy), FixtureDiscoveryFetcher(fixture), fixture_id="g25-seed-inputs-v1")
    assert result == replay
    assert result["query_count"] == 4
    candidates = result["candidates"]
    assert candidates[0]["candidate_id"] == "repo:4242"
    assert candidates[0]["rank_score"] > candidates[-1]["rank_score"]
    assert "RELEVANT_MATCH" in candidates[0]["rank_reasons"]
    kinds = {item["discovered_by"]["kind"] for item in candidates}
    assert {"capability", "repository", "engineer", "organization"} <= kinds
    engineer = next(item for item in candidates if item["discovered_by"]["kind"] == "engineer")
    assert engineer["authors"] == ["alice"]
    assert engineer["discovered_by"]["seed"] == "alice"
    duplicate = next(item for item in candidates if item["duplicate_of"])
    assert duplicate["correlation_metadata"]["duplicate_of"] == duplicate["duplicate_of"]
    assert all(item["source_scope"]["enabled"] is False for item in candidates)


def test_discovery_records_rename_aliases_and_rejects_malformed_items():
    fixture = {
        "schema_version": 1,
        "responses": {
            "durable execution": {
                "1": [
                    {
                        "id": 9,
                        "full_name": "newco/runtime",
                        "previous_full_name": "oldco/runtime",
                        "owner": {"login": "newco"},
                        "description": "Durable execution runtime",
                    },
                    "not-an-object",
                ]
            }
        },
    }
    policy = load_policy(dict(POLICY, query_terms=["durable execution"], max_pages_per_query=1))
    result = discover(policy, FixtureDiscoveryFetcher(fixture), fixture_id="rename-negative-v1")
    candidate = result["candidates"][0]
    assert candidate["aliases"] == ["oldco/runtime"]
    assert "malformed_item:durable execution:1" in result["stop_reasons"]


def test_transient_page_failure_retries_without_advancing_cursor():
    class RetryFetcher:
        def __init__(self):
            self.calls = []

        def search(self, query, *, page):
            self.calls.append((query, page))
            if len(self.calls) == 1:
                from riff.github_discovery import DiscoveryTransientError
                raise DiscoveryTransientError("temporary")
            return GitHubResponse([], {})

    fetcher = RetryFetcher()
    result = discover(load_policy(dict(POLICY, query_terms=["durable execution"], enabled=True)), fetcher)
    assert fetcher.calls == [("durable execution", 1), ("durable execution", 1)]
    assert result["retry_count"] == 1
    assert result["cursor_state"] == {"durable execution": 1}


def test_review_and_promotion_require_explicit_transitions(tmp_path):
    queue = {
        "schema_version": 1,
        "run_id": "discovery-test",
        "candidates": [{
            "candidate_id": "repo:1", "provider_repository_id": "1", "full_name": "acme/riff",
            "canonical_url": "https://github.com/acme/riff", "aliases": [], "organization": "acme",
            "root_id": "repo:1", "topics": ["agents"], "stars": 1, "is_fork": False,
            "is_mirror": False, "bot_only": False, "discovered_by": {"query": "agents"},
            "seed_source_id": "seed", "filter_reasons": [], "review_status": "NEW",
            "source_scope": {"endpoint": "https://api.github.com/repos/acme/riff", "enabled": False},
        }],
    }
    with pytest.raises(DiscoveryPolicyError, match="only APPROVED"):
        promote_candidates(queue, ["repo:1"], confirmation="PROMOTE", config={"schema_version": 1, "sources": []})
    approve_candidates(queue, ["repo:1"])
    result = promote_candidates(queue, ["repo:1"], confirmation="PROMOTE", config={"schema_version": 1, "sources": []})
    assert result["config"]["sources"][0]["enabled"] is False
    assert result["config"]["sources"][0]["discovered_by"] == {"query": "agents"}
    assert result["config"]["sources"][0]["correlation_metadata"] == {}
    assert result["queue"]["candidates"][0]["review_status"] == "PROMOTED"
    path = tmp_path / "queue.json"
    write_queue(path, queue)
    assert path.exists()
