"""Deterministic evaluation of bounded GitHub discovery strategies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class DiscoveryEvaluationError(ValueError):
    """The discovery benchmark is malformed or exceeds its declared bounds."""


REQUIRED_CANDIDATE_FIELDS = {
    "candidate_id",
    "provider_repository_id",
    "full_name",
    "organization",
    "root_id",
    "relevant",
    "is_fork",
    "is_mirror",
    "bot_only",
    "duplicate_of",
    "aliases",
    "artifact_ids",
}
REQUIRED_STRATEGY_FIELDS = {
    "strategy_id",
    "candidate_ids",
    "request_volume",
    "retry_count",
    "pages_examined",
    "cursor_replays",
    "cursor_replay_safe",
    "stop_reason",
}


def load_fixture(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryEvaluationError("GitHub discovery fixture could not be read") from exc
    validate_fixture(payload)
    return dict(payload)


def validate_fixture(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise DiscoveryEvaluationError("discovery fixture requires schema_version 1")
    candidates = payload.get("candidates")
    strategies = payload.get("strategies")
    bounds = payload.get("bounds")
    ground_truth = payload.get("ground_truth")
    if not isinstance(candidates, list) or not candidates:
        raise DiscoveryEvaluationError("discovery fixture requires candidates")
    if not isinstance(strategies, list) or len(strategies) < 3:
        raise DiscoveryEvaluationError("discovery fixture requires at least three strategies")
    if not isinstance(bounds, Mapping):
        raise DiscoveryEvaluationError("discovery fixture requires bounds")
    if not isinstance(ground_truth, list) or not ground_truth:
        raise DiscoveryEvaluationError("discovery fixture requires ground_truth")

    candidate_ids: set[str] = set()
    provider_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise DiscoveryEvaluationError(f"candidate {index} must be an object")
        missing = REQUIRED_CANDIDATE_FIELDS - set(candidate)
        if missing:
            raise DiscoveryEvaluationError(f"candidate {index} missing: {', '.join(sorted(missing))}")
        candidate_id = candidate["candidate_id"]
        provider_id = candidate["provider_repository_id"]
        if not isinstance(candidate_id, str) or not candidate_id.strip() or candidate_id in candidate_ids:
            raise DiscoveryEvaluationError(f"candidate {index} has an invalid or duplicate candidate_id")
        if not isinstance(provider_id, str) or not provider_id.strip() or provider_id in provider_ids:
            raise DiscoveryEvaluationError(f"candidate {candidate_id} has an invalid or duplicate provider_repository_id")
        candidate_ids.add(candidate_id)
        provider_ids.add(provider_id)
        if not isinstance(candidate["aliases"], list) or any(not isinstance(item, str) for item in candidate["aliases"]):
            raise DiscoveryEvaluationError(f"candidate {candidate_id} aliases must be a string list")
        if not isinstance(candidate["artifact_ids"], list) or any(not isinstance(item, str) for item in candidate["artifact_ids"]):
            raise DiscoveryEvaluationError(f"candidate {candidate_id} artifact_ids must be a string list")
        if candidate["duplicate_of"] is not None and candidate["duplicate_of"] not in candidate_ids | {item["candidate_id"] for item in candidates[:index]}:
            raise DiscoveryEvaluationError(f"candidate {candidate_id} references an unknown duplicate")

    truth = set(ground_truth)
    if not truth <= candidate_ids:
        raise DiscoveryEvaluationError("ground_truth references an unknown candidate")
    if any(not isinstance(value, bool) for value in (candidate["relevant"] for candidate in candidates)):
        raise DiscoveryEvaluationError("candidate relevant values must be booleans")
    if truth != {candidate["candidate_id"] for candidate in candidates if candidate["relevant"]}:
        raise DiscoveryEvaluationError("ground_truth must match candidate relevance labels")

    max_candidates = _positive_bound(bounds, "max_candidates_per_strategy")
    max_requests = _positive_bound(bounds, "max_requests_per_strategy")
    max_pages = _positive_bound(bounds, "max_pages_per_strategy")
    strategy_ids: set[str] = set()
    for index, strategy in enumerate(strategies):
        if not isinstance(strategy, Mapping):
            raise DiscoveryEvaluationError(f"strategy {index} must be an object")
        missing = REQUIRED_STRATEGY_FIELDS - set(strategy)
        if missing:
            raise DiscoveryEvaluationError(f"strategy {index} missing: {', '.join(sorted(missing))}")
        strategy_id = strategy["strategy_id"]
        if not isinstance(strategy_id, str) or not strategy_id.strip() or strategy_id in strategy_ids:
            raise DiscoveryEvaluationError(f"strategy {index} has an invalid or duplicate strategy_id")
        strategy_ids.add(strategy_id)
        ids = strategy["candidate_ids"]
        if not isinstance(ids, list) or not ids or len(ids) > max_candidates:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} exceeds candidate bound")
        if len(ids) != len(set(ids)) or not set(ids) <= candidate_ids:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} has unknown or duplicate candidates")
        if not isinstance(strategy["request_volume"], int) or not 0 < strategy["request_volume"] <= max_requests:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} exceeds request bound")
        if not isinstance(strategy["pages_examined"], int) or not 0 < strategy["pages_examined"] <= max_pages:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} exceeds page bound")
        if not isinstance(strategy["retry_count"], int) or strategy["retry_count"] < 0:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} has an invalid retry_count")
        if not isinstance(strategy["cursor_replays"], int) or strategy["cursor_replays"] < 0:
            raise DiscoveryEvaluationError(f"strategy {strategy_id} has an invalid cursor_replays")
        if not isinstance(strategy["cursor_replay_safe"], bool):
            raise DiscoveryEvaluationError(f"strategy {strategy_id} cursor_replay_safe must be boolean")


def evaluate_fixture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return stable metrics for every recorded discovery strategy."""

    validate_fixture(payload)
    candidates = {item["candidate_id"]: item for item in payload["candidates"]}
    truth = set(payload["ground_truth"])
    metrics: dict[str, Any] = {}
    for strategy in payload["strategies"]:
        selected = [candidates[item] for item in strategy["candidate_ids"]]
        metrics[strategy["strategy_id"]] = {
            "precision_at_3": _precision(selected, truth, 3),
            "precision_at_5": _precision(selected, truth, 5),
            "recall_at_3": _recall(selected, truth, 3),
            "recall_at_5": _recall(selected, truth, 5),
            "duplicate_or_correlated_rate_at_5": _duplicate_rate(selected[:5]),
            "root_diversity_at_5": _diversity(selected[:5], "root_id"),
            "organization_diversity_at_5": _diversity(selected[:5], "organization"),
            "bot_fork_contamination_at_5": _contamination(selected[:5]),
            "syndication_duplicate_rate_at_5": _syndication_rate(selected[:5]),
            "request_volume": strategy["request_volume"],
            "retry_count": strategy["retry_count"],
            "pages_examined": strategy["pages_examined"],
            "cursor_replays": strategy["cursor_replays"],
            "cursor_replay_safe": strategy["cursor_replay_safe"],
            "stop_reason": strategy["stop_reason"],
        }
    return {
        "schema_version": payload["schema_version"],
        "benchmark_id": payload.get("benchmark_id", "github-discovery"),
        "ground_truth_count": len(truth),
        "candidate_count": len(candidates),
        "strategies": metrics,
        "decision": payload.get("decision", {}),
    }


def _positive_bound(bounds: Mapping[str, Any], name: str) -> int:
    value = bounds.get(name)
    if not isinstance(value, int) or value < 1:
        raise DiscoveryEvaluationError(f"bounds.{name} must be a positive integer")
    return value


def _precision(selected: list[Mapping[str, Any]], truth: set[str], k: int) -> float:
    return round(sum(item["candidate_id"] in truth for item in selected[:k]) / k, 4)


def _recall(selected: list[Mapping[str, Any]], truth: set[str], k: int) -> float:
    return round(sum(item["candidate_id"] in truth for item in selected[:k]) / len(truth), 4)


def _duplicate_rate(selected: list[Mapping[str, Any]]) -> float:
    seen_roots: set[str] = set()
    duplicate_count = 0
    for item in selected:
        if item["duplicate_of"] is not None or item["root_id"] in seen_roots:
            duplicate_count += 1
        seen_roots.add(item["root_id"])
    return round(duplicate_count / 5, 4)


def _diversity(selected: list[Mapping[str, Any]], field: str) -> float:
    return round(len({item[field] for item in selected}) / 5, 4)


def _contamination(selected: list[Mapping[str, Any]]) -> float:
    return round(sum(item["is_fork"] or item["is_mirror"] or item["bot_only"] for item in selected) / 5, 4)


def _syndication_rate(selected: list[Mapping[str, Any]]) -> float:
    return round(sum(item["duplicate_of"] is not None for item in selected) / 5, 4)
