from riff.github_monitoring import CandidateDisposition, GitHubMonitoringError, QuantitativeRule, evaluate_quantitative_search


def test_quantitative_search_filters_noise_and_preserves_provenance():
    result = evaluate_quantitative_search(
        [
            {"id": "1", "full_name": "acme/durable", "html_url": "https://github.com/acme/durable", "independent_roots": ["a", "b"], "source_count": 2, "relevant": True},
            {"id": "2", "full_name": "mirror/durable", "html_url": "https://github.com/mirror/durable", "independent_roots": ["a", "b"], "source_count": 2, "is_mirror": True},
            {"id": "3", "full_name": "popular/noise", "html_url": "https://github.com/popular/noise", "independent_roots": ["a"], "stars": 100_000},
        ],
        query="durable agents",
        rule=QuantitativeRule("rule-1", "policy-1", popularity_only_stars=50_000),
    )
    assert len(result["accepted"]) == 1
    assert result["accepted"][0]["disposition"] == CandidateDisposition.AUTO_QUEUED
    assert result["accepted"][0]["threshold_evaluation"]["query"] == "durable agents"
    assert {"MIRROR", "POPULARITY_ONLY", "INSUFFICIENT_INDEPENDENCE"} <= {reason for item in result["rejected"] for reason in item["threshold_evaluation"]["reasons"]}


def test_disabled_scope_search_requires_reviewable_provenance():
    result = evaluate_quantitative_search(
        [{"id": "1", "full_name": "lab/agents", "html_url": "https://github.com/lab/agents", "root_id": "lab", "source_count": 1}],
        query="agents",
        rule=QuantitativeRule("rule-2", "policy-2", min_independent_roots=1, action="PROPOSE_DISABLED_SCOPE"),
    )
    assert result["accepted"][0]["disposition"] == CandidateDisposition.DISABLED_SCOPE_PROPOSED


def test_search_bounds_are_rejected_before_network_or_storage():
    try:
        evaluate_quantitative_search([], query="agents", rule=QuantitativeRule("", "policy"))
    except GitHubMonitoringError as exc:
        assert "rule_id" in str(exc)
    else:
        raise AssertionError("invalid rule should fail")
