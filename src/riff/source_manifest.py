"""Validation for the reviewed, secret-free ingestion source manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


SOURCE_TYPES = {"TECHNICAL_WRITING", "GITHUB", "JOBS"}
PERMISSION_STATUSES = {"CONFIRMED", "USER_PROVIDED", "PENDING_REVIEW", "UNAVAILABLE"}
REQUIRED_FIELDS = {
    "source_id", "name", "source_type", "endpoint_or_scope", "access_method",
    "permission_status", "retention_mode", "cadence", "expected_artifacts",
    "identity_fields", "fixture_plan", "rate_limit_policy", "fallback",
}
SECRET_RE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]|://[^/\s:@]+:[^/\s@]+@")


class SourceManifestError(ValueError):
    """The source plan is incomplete, unsafe, or structurally invalid."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(payload)
    return payload


def validate_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("sources"), list):
        raise SourceManifestError("source manifest requires schema_version 1 and sources")
    if len(payload["sources"]) < 5:
        raise SourceManifestError("source manifest requires at least five concrete scopes")
    ids: set[str] = set()
    categories: set[str] = set()
    for index, entry in enumerate(payload["sources"]):
        if not isinstance(entry, Mapping):
            raise SourceManifestError(f"source {index} must be an object")
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise SourceManifestError(f"source {index} missing: {', '.join(sorted(missing))}")
        source_id = entry["source_id"]
        if not isinstance(source_id, str) or not source_id.strip() or source_id in ids:
            raise SourceManifestError(f"source {index} has an invalid or duplicate source_id")
        ids.add(source_id)
        source_type = entry["source_type"]
        if source_type not in SOURCE_TYPES:
            raise SourceManifestError(f"source {source_id} has an unsupported source_type")
        categories.add(source_type)
        if entry["permission_status"] not in PERMISSION_STATUSES:
            raise SourceManifestError(f"source {source_id} has an invalid permission_status")
        for field in ("endpoint_or_scope", "access_method", "retention_mode", "cadence", "fixture_plan", "rate_limit_policy", "fallback"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise SourceManifestError(f"source {source_id} requires non-empty {field}")
        for field in ("expected_artifacts", "identity_fields"):
            if not isinstance(entry[field], list) or not entry[field] or any(not isinstance(item, str) or not item.strip() for item in entry[field]):
                raise SourceManifestError(f"source {source_id} requires a non-empty {field} list")
        blob = json.dumps(entry, sort_keys=True)
        if SECRET_RE.search(blob):
            raise SourceManifestError(f"source {source_id} contains a credential-like value")
    if categories != SOURCE_TYPES:
        raise SourceManifestError("source manifest must cover TECHNICAL_WRITING, GITHUB, and JOBS")
