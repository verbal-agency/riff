"""Deterministic evaluation of bounded GitHub discovery strategies."""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .github_ingestion import GitHubResponse


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


# G20 implementation -------------------------------------------------------

class DiscoveryPolicyError(ValueError):
    """A discovery policy, response, or review transition is invalid."""


class DiscoveryTransientError(RuntimeError):
    """A discovery request can be retried without changing the policy."""


class DiscoveryPermanentError(RuntimeError):
    """A discovery request or response cannot be retried safely."""


class DiscoveryFetcher(Protocol):
    def search(self, query: str, *, page: int) -> GitHubResponse:
        ...


@dataclass(frozen=True, slots=True)
class DiscoveryPolicy:
    schema_version: int
    policy_id: str
    query_terms: tuple[str, ...]
    seed_source_ids: tuple[str, ...]
    max_pages_per_query: int
    max_candidates_per_query: int
    max_requests: int
    max_contributor_expansion: int
    retry_limit: int
    stop_rules: dict[str, Any]
    review_required: bool
    enabled: bool
    popularity_only_stars: int = 50_000
    max_queries: int = 3
    capability_terms: tuple[str, ...] = ()
    repository_seeds: tuple[str, ...] = ()
    engineer_seeds: tuple[str, ...] = ()
    organization_seeds: tuple[str, ...] = ()


@dataclass
class DiscoveryCandidate:
    candidate_id: str
    provider_repository_id: str
    full_name: str
    canonical_url: str
    aliases: list[str]
    organization: str | None
    root_id: str
    topics: list[str]
    stars: int | None
    is_fork: bool
    is_mirror: bool
    bot_only: bool
    discovered_by: dict[str, Any]
    seed_source_id: str | None
    filter_reasons: list[str] = field(default_factory=list)
    review_status: str = "NEW"
    source_scope: dict[str, Any] = field(default_factory=dict)
    duplicate_of: str | None = None
    relevant: bool = False
    authors: list[str] = field(default_factory=list)
    correlation_metadata: dict[str, Any] = field(default_factory=dict)
    uncertainty: list[str] = field(default_factory=list)
    relevance_reasons: list[str] = field(default_factory=list)
    rank_score: int = 0
    rank_reasons: list[str] = field(default_factory=list)


def load_policy(path_or_payload: str | Path | Mapping[str, Any]) -> DiscoveryPolicy:
    if isinstance(path_or_payload, Mapping):
        payload = dict(path_or_payload)
    else:
        try:
            payload = json.loads(Path(path_or_payload).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiscoveryPolicyError("GitHub discovery policy could not be read") from exc
    if payload.get("schema_version") != 1:
        raise DiscoveryPolicyError("discovery policy requires schema_version 1")
    required = {
        "policy_id", "seed_source_ids", "max_pages_per_query",
        "max_candidates_per_query", "max_requests", "max_contributor_expansion",
        "retry_limit", "stop_rules", "review_required", "enabled",
    }
    missing = required - set(payload)
    if missing:
        raise DiscoveryPolicyError(f"discovery policy missing: {', '.join(sorted(missing))}")
    if "query_terms" not in payload and "capability_terms" not in payload:
        raise DiscoveryPolicyError("discovery policy requires query_terms or capability_terms")
    terms = payload.get("query_terms", payload.get("capability_terms", []))
    seeds = payload["seed_source_ids"]
    if not isinstance(terms, list) or not 1 <= len(terms) <= 3 or any(not isinstance(item, str) or not item.strip() for item in terms):
        raise DiscoveryPolicyError("query_terms or capability_terms must contain one to three non-empty strings")
    capability_terms = payload.get("capability_terms", terms)
    if not isinstance(capability_terms, list) or any(not isinstance(item, str) or not item.strip() for item in capability_terms):
        raise DiscoveryPolicyError("capability_terms must be a string list")
    if not isinstance(seeds, list) or any(not isinstance(item, str) or not item.strip() for item in seeds):
        raise DiscoveryPolicyError("seed_source_ids must be a string list")
    seed_fields = {
        "repository_seeds": payload.get("repository_seeds", []),
        "engineer_seeds": payload.get("engineer_seeds", []),
        "organization_seeds": payload.get("organization_seeds", []),
    }
    for name, values in seed_fields.items():
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise DiscoveryPolicyError(f"{name} must be a string list")
    bounds = {
        "max_pages_per_query": (1, 2),
        "max_candidates_per_query": (1, 6),
        "max_requests": (1, 10),
        "max_contributor_expansion": (0, 2),
        "retry_limit": (0, 3),
    }
    for name, (minimum, maximum) in bounds.items():
        value = payload[name]
        if not isinstance(value, int) or not minimum <= value <= maximum:
            raise DiscoveryPolicyError(f"{name} must be between {minimum} and {maximum}")
    max_queries = payload.get("max_queries", len(terms) + sum(len(values) for values in seed_fields.values()))
    if not isinstance(max_queries, int) or not 1 <= max_queries <= 8:
        raise DiscoveryPolicyError("max_queries must be between 1 and 8")
    if not isinstance(payload["stop_rules"], Mapping):
        raise DiscoveryPolicyError("stop_rules must be an object")
    if not isinstance(payload["review_required"], bool) or payload["review_required"] is not True:
        raise DiscoveryPolicyError("review_required must remain true")
    if not isinstance(payload["enabled"], bool):
        raise DiscoveryPolicyError("enabled must be boolean")
    popularity = payload.get("popularity_only_stars", 50_000)
    if not isinstance(popularity, int) or popularity < 1:
        raise DiscoveryPolicyError("popularity_only_stars must be positive")
    return DiscoveryPolicy(
        schema_version=1,
        policy_id=str(payload["policy_id"]),
        query_terms=tuple(item.strip() for item in terms),
        seed_source_ids=tuple(item.strip() for item in seeds),
        max_pages_per_query=payload["max_pages_per_query"],
        max_candidates_per_query=payload["max_candidates_per_query"],
        max_requests=payload["max_requests"],
        max_contributor_expansion=payload["max_contributor_expansion"],
        retry_limit=payload["retry_limit"],
        stop_rules=dict(payload["stop_rules"]),
        review_required=True,
        enabled=payload["enabled"],
        popularity_only_stars=popularity,
        max_queries=max_queries,
        capability_terms=tuple(item.strip() for item in capability_terms),
        repository_seeds=tuple(item.strip() for item in seed_fields["repository_seeds"]),
        engineer_seeds=tuple(item.strip() for item in seed_fields["engineer_seeds"]),
        organization_seeds=tuple(item.strip() for item in seed_fields["organization_seeds"]),
    )


class FixtureDiscoveryFetcher:
    """Search client backed entirely by a recorded discovery fixture."""

    def __init__(self, fixture: Mapping[str, Any] | str | Path):
        if not isinstance(fixture, Mapping):
            try:
                fixture = json.loads(Path(fixture).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DiscoveryPolicyError("discovery response fixture could not be read") from exc
        if fixture.get("schema_version") != 1 or not isinstance(fixture.get("responses"), Mapping):
            raise DiscoveryPolicyError("discovery response fixture requires schema_version 1 and responses")
        self.responses = fixture["responses"]
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, *, page: int) -> GitHubResponse:
        self.calls.append((query, page))
        response = self.responses.get(query)
        if not isinstance(response, Mapping):
            raise DiscoveryPermanentError(f"no recorded response for query: {query}")
        page_value = response.get(str(page), response.get(page))
        if isinstance(page_value, Mapping) and "error" in page_value:
            kind = page_value["error"]
            if kind == "transient":
                raise DiscoveryTransientError(f"transient fixture failure for {query} page {page}")
            raise DiscoveryPermanentError(f"permanent fixture failure for {query} page {page}")
        if page_value is None:
            return GitHubResponse([], {})
        if not isinstance(page_value, list):
            raise DiscoveryPermanentError(f"fixture page for {query} must be a list")
        return GitHubResponse(page_value, {})


class HttpGitHubDiscoveryFetcher:
    """Thin adapter that keeps discovery on the existing bounded REST client."""

    def __init__(self, *, token: str | None = None):
        from .github_ingestion import HttpGitHubFetcher

        self._fetcher = HttpGitHubFetcher(token=token)

    def search(self, query: str, *, page: int) -> GitHubResponse:
        return self._fetcher.fetch("/search/repositories", params={"q": query, "page": page, "per_page": 100})


def discover(policy: DiscoveryPolicy | Mapping[str, Any] | str | Path, fetcher: DiscoveryFetcher, *, fixture_id: str | None = None) -> dict[str, Any]:
    """Run bounded topic/text discovery and return a JSON-serializable queue."""

    if not isinstance(policy, DiscoveryPolicy):
        policy = load_policy(policy)
    if not policy.enabled and fixture_id is None and isinstance(fetcher, FixtureDiscoveryFetcher) is False:
        raise DiscoveryPolicyError("live discovery is disabled by policy")
    identity = {
        "policy_id": policy.policy_id,
        "query_terms": policy.query_terms,
        "seed_source_ids": policy.seed_source_ids,
        "capability_terms": policy.capability_terms,
        "repository_seeds": policy.repository_seeds,
        "engineer_seeds": policy.engineer_seeds,
        "organization_seeds": policy.organization_seeds,
        "max_queries": policy.max_queries,
        "fixture_id": fixture_id,
    }
    run_id = "discovery-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    candidates: list[DiscoveryCandidate] = []
    requests = retries = pages = 0
    stop_reasons: list[str] = []
    cursor_state: dict[str, int] = {}
    queries = _discovery_queries(policy)
    for term_index, (query, seed, discovery_kind, seed_value) in enumerate(queries[: policy.max_queries]):
        query_count = 0
        for page in range(1, policy.max_pages_per_query + 1):
            if requests >= policy.max_requests:
                stop_reasons.append("request_bound_reached")
                break
            attempt = 0
            while True:
                requests += 1
                try:
                    response = fetcher.search(query, page=page)
                    break
                except DiscoveryTransientError:
                    retries += 1
                    attempt += 1
                    if attempt > policy.retry_limit or requests >= policy.max_requests:
                        stop_reasons.append(f"transient_failure:{query}:{page}")
                        response = None
                        break
                except Exception as exc:
                    stop_reasons.append(f"permanent_failure:{query}:{page}")
                    response = None
                    break
            if response is None:
                break
            pages += 1
            cursor_state[query] = page
            if not isinstance(response.data, list):
                stop_reasons.append(f"malformed_response:{query}:{page}")
                break
            if not response.data:
                break
            for raw in response.data:
                if query_count >= policy.max_candidates_per_query:
                    stop_reasons.append(f"candidate_bound_reached:{query}")
                    break
                try:
                    candidate = _normalize_discovery_candidate(
                        raw,
                        query=query,
                        page=page,
                        seed_source_id=seed,
                        discovery_kind=discovery_kind,
                        seed_value=seed_value,
                        policy=policy,
                    )
                except DiscoveryPermanentError:
                    stop_reasons.append(f"malformed_item:{query}:{page}")
                    continue
                prior = sum(1 for item in candidates if item.provider_repository_id == candidate.provider_repository_id)
                if prior:
                    candidate.candidate_id = f"{candidate.candidate_id}:duplicate-{prior}"
                candidates.append(candidate)
                query_count += 1
            if query_count >= policy.max_candidates_per_query:
                break
        if requests >= policy.max_requests:
            break
    _deduplicate_candidates(candidates)
    _apply_root_concentration(candidates, policy)
    _rank_candidates(candidates)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "policy_id": policy.policy_id,
        "policy_version": "github-discovery-v1",
        "query_terms": list(policy.query_terms),
        "discovery_inputs": {
            "capability_terms": list(policy.capability_terms),
            "repository_seeds": list(policy.repository_seeds),
            "engineer_seeds": list(policy.engineer_seeds),
            "organization_seeds": list(policy.organization_seeds),
        },
        "query_count": min(len(queries), policy.max_queries),
        "request_count": requests,
        "retry_count": retries,
        "pages_examined": pages,
        "cursor_state": cursor_state,
        "stop_reasons": sorted(set(stop_reasons)) or ["query_and_page_bound_reached"],
        "candidates": [asdict(item) for item in sorted(candidates, key=_candidate_sort_key)],
    }


def _discovery_queries(policy: DiscoveryPolicy) -> list[tuple[str, str | None, str, str]]:
    """Build bounded GitHub search queries with explicit seed provenance."""

    queries: list[tuple[str, str | None, str, str]] = []
    seen: set[str] = set()
    for term_index, term in enumerate(policy.capability_terms or policy.query_terms):
        if term in seen:
            continue
        seen.add(term)
        seed = policy.seed_source_ids[term_index % len(policy.seed_source_ids)] if policy.seed_source_ids else None
        queries.append((term, seed, "capability", term))
    for kind, values, prefix in (
        ("repository", policy.repository_seeds, "repo"),
        ("engineer", policy.engineer_seeds, "user"),
        ("organization", policy.organization_seeds, "org"),
    ):
        for value in values:
            query = value if value.startswith(f"{prefix}:") else f"{prefix}:{value}"
            if query in seen:
                continue
            seen.add(query)
            queries.append((query, None, kind, value))
    return queries


def _normalize_discovery_candidate(
    raw: Any,
    *,
    query: str,
    page: int,
    seed_source_id: str | None,
    discovery_kind: str,
    seed_value: str,
    policy: DiscoveryPolicy,
) -> DiscoveryCandidate:
    if not isinstance(raw, Mapping):
        raise DiscoveryPermanentError("repository search item must be an object")
    provider_id = str(raw.get("id") or raw.get("provider_repository_id") or "").strip()
    full_name = str(raw.get("full_name") or "").strip()
    if not provider_id or not full_name or "/" not in full_name:
        raise DiscoveryPermanentError("repository search item lacks stable identity")
    owner = raw.get("owner") if isinstance(raw.get("owner"), Mapping) else {}
    organization = str(raw.get("organization") or owner.get("login") or full_name.split("/", 1)[0]) or None
    canonical = str(raw.get("html_url") or raw.get("canonical_url") or f"https://github.com/{full_name}").strip()
    parent = raw.get("parent") if isinstance(raw.get("parent"), Mapping) else raw.get("source") if isinstance(raw.get("source"), Mapping) else {}
    root_id = f"repo:{parent.get('id')}" if raw.get("fork") and parent.get("id") else f"repo:{provider_id}"
    topics = raw.get("topics") if isinstance(raw.get("topics"), list) else []
    topics = sorted({str(item).strip() for item in topics if str(item).strip()})
    description = str(raw.get("description") or "")
    haystack = " ".join([full_name, description, " ".join(topics)]).lower()
    query_tokens = [token for token in re.split(r"[^a-z0-9]+", query.lower()) if token]
    relevant = bool(raw.get("relevant")) if "relevant" in raw else all(token in haystack for token in query_tokens[:3])
    owner_login = str(owner.get("login") or organization or "")
    bot_only = bool(raw.get("bot_only")) or str(owner.get("type") or "").lower() == "bot" or owner_login.endswith("[bot]") or "bot" in owner_login.lower()
    is_fork = bool(raw.get("fork", raw.get("is_fork", False)))
    is_mirror = bool(raw.get("is_mirror", False) or raw.get("mirror_url"))
    stars = raw.get("stargazers_count", raw.get("stars"))
    stars = int(stars) if isinstance(stars, int) and stars >= 0 else None
    reasons: list[str] = []
    if is_fork:
        reasons.append("FORK")
    if is_mirror:
        reasons.append("MIRROR")
    if bot_only:
        reasons.append("BOT")
    if stars is not None and stars >= policy.popularity_only_stars and not relevant:
        reasons.append("POPULARITY_ONLY")
    relevance_reasons: list[str] = []
    if relevant:
        relevance_reasons.append("EXPLICIT_RELEVANCE" if "relevant" in raw else "QUERY_TERM_MATCH")
    else:
        relevance_reasons.append("NO_QUERY_TERM_MATCH")
    uncertainty: list[str] = []
    if not description and not topics:
        uncertainty.append("LIMITED_METADATA")
    if discovery_kind in {"engineer", "organization"} and not raw.get("contributors") and not raw.get("authors"):
        uncertainty.append("ATTRIBUTION_NOT_VERIFIED")
    authors_raw = raw.get("authors", raw.get("contributors", raw.get("maintainers", [])))
    authors = sorted({str(item.get("login") if isinstance(item, Mapping) else item).strip() for item in authors_raw if str(item.get("login") if isinstance(item, Mapping) else item).strip()}) if isinstance(authors_raw, list) else []
    correlation_metadata = {
        "root_id": root_id,
        "provider_repository_id": provider_id,
        "duplicate_of": None,
        "artifact_ids": raw.get("artifact_ids", []),
        "fork_or_mirror": is_fork or is_mirror,
    }
    aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
    aliases = sorted({str(item).strip() for item in aliases if str(item).strip()} | ({str(raw["previous_full_name"])} if raw.get("previous_full_name") else set()))
    return DiscoveryCandidate(
        candidate_id=f"repo:{provider_id}",
        provider_repository_id=provider_id,
        full_name=full_name,
        canonical_url=canonical,
        aliases=aliases,
        organization=organization,
        root_id=root_id,
        topics=topics,
        stars=stars,
        is_fork=is_fork,
        is_mirror=is_mirror,
        bot_only=bot_only,
        discovered_by={"query": query, "page": page, "kind": discovery_kind, "seed": seed_value},
        seed_source_id=seed_source_id,
        filter_reasons=reasons,
        review_status="FILTERED" if reasons else "NEW",
        source_scope={"endpoint": f"https://api.github.com/repos/{full_name}", "enabled": False},
        relevant=relevant,
        authors=authors,
        correlation_metadata=correlation_metadata,
        uncertainty=uncertainty,
        relevance_reasons=relevance_reasons,
        rank_score=_rank_score(relevant=relevant, filter_reasons=reasons, uncertainty=uncertainty, discovery_kind=discovery_kind),
        rank_reasons=_rank_reasons(relevant=relevant, filter_reasons=reasons, uncertainty=uncertainty, discovery_kind=discovery_kind),
    )


def _rank_score(*, relevant: bool, filter_reasons: list[str], uncertainty: list[str], discovery_kind: str) -> int:
    score = 3 if relevant else 0
    if discovery_kind in {"repository", "engineer", "organization"}:
        score += 1
    score -= 2 * len(filter_reasons)
    score -= len(uncertainty)
    return score


def _rank_reasons(*, relevant: bool, filter_reasons: list[str], uncertainty: list[str], discovery_kind: str) -> list[str]:
    reasons: list[str] = []
    if relevant:
        reasons.append("RELEVANT_MATCH")
    if discovery_kind != "capability":
        reasons.append(f"SEEDED_{discovery_kind.upper()}")
    reasons.extend(f"FILTERED_{item}" for item in filter_reasons)
    reasons.extend(f"UNCERTAIN_{item}" for item in uncertainty)
    return reasons or ["UNSCORED"]


def _candidate_sort_key(candidate: DiscoveryCandidate) -> tuple[int, str, str]:
    return (-candidate.rank_score, candidate.candidate_id, candidate.full_name)


def _rank_candidates(candidates: list[DiscoveryCandidate]) -> None:
    """Attach stable scores without allowing popularity to create relevance."""

    for candidate in candidates:
        candidate.rank_score = _rank_score(
            relevant=candidate.relevant,
            filter_reasons=candidate.filter_reasons,
            uncertainty=candidate.uncertainty,
            discovery_kind=str(candidate.discovered_by.get("kind", "capability")),
        )
        candidate.rank_reasons = _rank_reasons(
            relevant=candidate.relevant,
            filter_reasons=candidate.filter_reasons,
            uncertainty=candidate.uncertainty,
            discovery_kind=str(candidate.discovered_by.get("kind", "capability")),
        )


def _deduplicate_candidates(candidates: list[DiscoveryCandidate]) -> None:
    by_provider: dict[str, DiscoveryCandidate] = {}
    by_alias: dict[str, DiscoveryCandidate] = {}
    for candidate in candidates:
        existing = by_provider.get(candidate.provider_repository_id)
        if existing and existing is not candidate:
            candidate.duplicate_of = existing.candidate_id
            candidate.correlation_metadata["duplicate_of"] = existing.candidate_id
            candidate.filter_reasons.append("DUPLICATE_PROVIDER_ID")
            candidate.review_status = "FILTERED"
            existing.aliases = sorted(set(existing.aliases + candidate.aliases + [candidate.full_name]))
            continue
        by_provider[candidate.provider_repository_id] = candidate
        aliases = {candidate.canonical_url, candidate.full_name, *candidate.aliases}
        duplicate = next((by_alias[item] for item in aliases if item in by_alias), None)
        if duplicate and duplicate is not candidate:
            candidate.duplicate_of = duplicate.candidate_id
            candidate.correlation_metadata["duplicate_of"] = duplicate.candidate_id
            candidate.filter_reasons.append("DUPLICATE_ALIAS")
            candidate.review_status = "FILTERED"
        for item in aliases:
            by_alias[item] = duplicate or candidate


def _apply_root_concentration(candidates: list[DiscoveryCandidate], policy: DiscoveryPolicy) -> None:
    threshold = policy.stop_rules.get("root_concentration_threshold", 1.0)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
        return
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.root_id] = counts.get(candidate.root_id, 0) + 1
    total = len(candidates) or 1
    for root_id, count in counts.items():
        if count / total <= threshold:
            continue
        seen = False
        for candidate in candidates:
            if candidate.root_id != root_id:
                continue
            if seen and "ROOT_CONCENTRATION" not in candidate.filter_reasons:
                candidate.filter_reasons.append("ROOT_CONCENTRATION")
                candidate.review_status = "FILTERED"
            seen = True


def validate_queue(queue: Mapping[str, Any]) -> None:
    if queue.get("schema_version") != 1 or not isinstance(queue.get("candidates"), list):
        raise DiscoveryPolicyError("review queue requires schema_version 1 and candidates")
    ids: set[str] = set()
    for item in queue["candidates"]:
        if not isinstance(item, Mapping):
            raise DiscoveryPolicyError("review queue candidate must be an object")
        required = {"candidate_id", "provider_repository_id", "full_name", "canonical_url", "review_status", "source_scope"}
        missing = required - set(item)
        if missing:
            raise DiscoveryPolicyError(f"review queue candidate missing: {', '.join(sorted(missing))}")
        if item["candidate_id"] in ids:
            raise DiscoveryPolicyError("review queue contains duplicate candidate_id")
        ids.add(item["candidate_id"])
        if item["review_status"] not in {"NEW", "FILTERED", "REJECTED", "APPROVED", "PROMOTED"}:
            raise DiscoveryPolicyError("review queue contains invalid review status")


def write_queue(path: str | Path, queue: Mapping[str, Any]) -> None:
    validate_queue(queue)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_queue(path: str | Path) -> dict[str, Any]:
    try:
        queue = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryPolicyError("review queue could not be read") from exc
    validate_queue(queue)
    return queue


def approve_candidates(queue: dict[str, Any], candidate_ids: list[str]) -> dict[str, Any]:
    validate_queue(queue)
    requested = set(candidate_ids)
    found = {item["candidate_id"] for item in queue["candidates"]}
    unknown = requested - found
    if unknown:
        raise DiscoveryPolicyError(f"unknown candidate(s): {', '.join(sorted(unknown))}")
    for item in queue["candidates"]:
        if item["candidate_id"] in requested:
            if item["review_status"] != "NEW":
                raise DiscoveryPolicyError(f"candidate {item['candidate_id']} is not reviewable")
            if item.get("filter_reasons"):
                raise DiscoveryPolicyError(f"candidate {item['candidate_id']} is filtered and cannot be approved")
            item["review_status"] = "APPROVED"
    return queue


def promote_candidates(queue: dict[str, Any], candidate_ids: list[str], *, confirmation: str, config: Mapping[str, Any], apply: bool = False) -> dict[str, Any]:
    validate_queue(queue)
    if confirmation != "PROMOTE":
        raise DiscoveryPolicyError("promotion requires confirmation token PROMOTE")
    requested = set(candidate_ids)
    projected_queue = json.loads(json.dumps(queue))
    selected = [item for item in projected_queue["candidates"] if item["candidate_id"] in requested]
    if len(selected) != len(requested):
        raise DiscoveryPolicyError("promotion contains an unknown candidate")
    if any(item["review_status"] != "APPROVED" for item in selected):
        raise DiscoveryPolicyError("only APPROVED candidates may be promoted")
    if config.get("schema_version") != 1 or not isinstance(config.get("sources"), list):
        raise DiscoveryPolicyError("GitHub source registry requires schema_version 1 and sources")
    projected = json.loads(json.dumps(config))
    existing = {item.get("source_id"): item for item in projected["sources"]}
    for item in selected:
        source_id = f"github-discovered-{item['provider_repository_id']}"
        existing[source_id] = {
            "source_id": source_id,
            "name": f"Discovered GitHub repository: {item['full_name']}",
            "source_type": "GITHUB",
            "endpoint": item["source_scope"]["endpoint"],
            "endpoint_or_scope": item["source_scope"]["endpoint"],
            "access_method": "Read-only GitHub REST API for one reviewed public repository",
            "permission_status": "PENDING_REVIEW",
            "enabled": False,
            "retention_mode": "Store bounded repository artifacts with canonical URLs",
            "cadence": "daily",
            "fixture_plan": "Recorded discovery and collector fixtures",
            "discovery_run_id": queue.get("run_id"),
            "discovered_by": item.get("discovered_by"),
            "authors": item.get("authors", []),
            "correlation_metadata": item.get("correlation_metadata", {}),
            "uncertainty": item.get("uncertainty", []),
            "provider_repository_id": item["provider_repository_id"],
        }
        item["review_status"] = "PROMOTED"
    projected["sources"] = sorted(existing.values(), key=lambda value: value.get("source_id", ""))
    return {"config": projected, "queue": projected_queue, "promoted": sorted(requested), "applied": apply}


# Stable descriptive aliases for callers that prefer verb-oriented names.
validate_policy = load_policy
run_discovery = discover
