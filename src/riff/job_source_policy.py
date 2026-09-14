"""Versioned, fail-closed policy for automated job collection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


class JobPolicyError(ValueError):
    """A job source policy is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class JobSource:
    source_id: str
    name: str
    source_kind: str
    endpoint: str | None
    enabled: bool
    allowlist: tuple[str, ...]
    terms_review: str
    robots_review: str
    cadence: str
    bounds: dict[str, int]
    retry_policy: dict[str, Any]
    retention: str
    fixture_reference: str
    fallback: str


@dataclass(frozen=True, slots=True)
class JobSourcePolicy:
    schema_version: int
    policy_id: str
    sources: tuple[JobSource, ...]

    def source(self, source_id: str) -> JobSource:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise JobPolicyError(f"unknown job source: {source_id}")


def load_policy(path_or_payload: str | Path | Mapping[str, Any]) -> JobSourcePolicy:
    if isinstance(path_or_payload, Mapping):
        payload = dict(path_or_payload)
    else:
        try:
            payload = json.loads(Path(path_or_payload).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JobPolicyError("job source policy could not be read") from exc
    validate_policy(payload)
    sources: list[JobSource] = []
    for item in payload["sources"]:
        bounds = dict(item["bounds"])
        sources.append(
            JobSource(
                source_id=item["source_id"],
                name=item["name"],
                source_kind=item["source_kind"],
                endpoint=item.get("endpoint"),
                enabled=bool(item["enabled"]),
                allowlist=tuple(item["allowlist"]),
                terms_review=item["terms_review"],
                robots_review=item["robots_review"],
                cadence=item["cadence"],
                bounds=bounds,
                retry_policy=dict(item["retry_policy"]),
                retention=item["retention"],
                fixture_reference=item["fixture_reference"],
                fallback=item["fallback"],
            )
        )
    return JobSourcePolicy(2, payload["policy_id"], tuple(sources))


def validate_policy(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 2 or not isinstance(payload.get("sources"), list):
        raise JobPolicyError("job source policy requires schema_version 2 and sources")
    if not isinstance(payload.get("policy_id"), str) or not payload["policy_id"].strip():
        raise JobPolicyError("job source policy requires policy_id")
    if not payload["sources"]:
        raise JobPolicyError("job source policy requires at least one source")
    required = {
        "source_id", "name", "source_kind", "enabled", "allowlist", "terms_review",
        "robots_review", "cadence", "bounds", "retry_policy", "retention",
        "fixture_reference", "fallback",
    }
    ids: set[str] = set()
    kinds: set[str] = set()
    for index, item in enumerate(payload["sources"]):
        if not isinstance(item, Mapping):
            raise JobPolicyError(f"source {index} must be an object")
        missing = required - set(item)
        if missing:
            raise JobPolicyError(f"source {index} missing: {', '.join(sorted(missing))}")
        source_id = item["source_id"]
        if not isinstance(source_id, str) or not source_id.strip() or source_id in ids:
            raise JobPolicyError(f"source {index} has an invalid or duplicate source_id")
        ids.add(source_id)
        kind = item["source_kind"]
        if kind not in {"API", "RSS", "HTML", "USER_URL"}:
            raise JobPolicyError(f"source {source_id} has unsupported source_kind")
        kinds.add(kind)
        if not isinstance(item["enabled"], bool):
            raise JobPolicyError(f"source {source_id} enabled must be boolean")
        if not isinstance(item["allowlist"], list) or any(not isinstance(host, str) or not host.strip() for host in item["allowlist"]):
            raise JobPolicyError(f"source {source_id} allowlist must be a string list")
        if kind == "USER_URL" and not item["allowlist"]:
            raise JobPolicyError(f"USER_URL source {source_id} requires an allowlist")
        if kind != "USER_URL" and not isinstance(item.get("endpoint"), str):
            raise JobPolicyError(f"source {source_id} requires endpoint")
        if kind != "USER_URL":
            endpoint = urlsplit(item["endpoint"])
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                raise JobPolicyError(f"source {source_id} endpoint must be an HTTP(S) URL")
            host = endpoint.hostname.lower().rstrip(".")
            if not any(host == allowed.lower().rstrip(".") or host.endswith("." + allowed.lower().rstrip(".")) for allowed in item["allowlist"]):
                raise JobPolicyError(f"source {source_id} endpoint host is not in the allowlist")
        if item["enabled"] and item["terms_review"] not in {"CONFIRMED", "USER_PROVIDED"}:
            raise JobPolicyError(f"enabled source {source_id} lacks terms review")
        if item["enabled"] and item["robots_review"] not in {"CONFIRMED", "NOT_APPLICABLE", "USER_PROVIDED"}:
            raise JobPolicyError(f"enabled source {source_id} lacks robots review")
        bounds = item["bounds"]
        if not isinstance(bounds, Mapping):
            raise JobPolicyError(f"source {source_id} bounds must be an object")
        for name, minimum, maximum in (
            ("max_requests", 1, 10), ("max_pages", 1, 2), ("max_items", 1, 100),
            ("max_body_bytes", 1, 2_000_000), ("max_redirects", 0, 5), ("timeout_seconds", 1, 120),
        ):
            value = bounds.get(name)
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise JobPolicyError(f"source {source_id} bounds.{name} must be between {minimum} and {maximum}")
        retry = item["retry_policy"]
        if not isinstance(retry, Mapping) or not isinstance(retry.get("max_attempts"), int) or not 0 <= retry["max_attempts"] <= 3:
            raise JobPolicyError(f"source {source_id} retry_policy.max_attempts must be between 0 and 3")
        for name in ("name", "terms_review", "robots_review", "cadence", "retention", "fixture_reference", "fallback"):
            if not isinstance(item[name], str) or not item[name].strip():
                raise JobPolicyError(f"source {source_id} requires non-empty {name}")
    if "USER_URL" not in kinds:
        raise JobPolicyError("job source policy requires a USER_URL source")
