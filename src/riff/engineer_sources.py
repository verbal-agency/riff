"""Validation for the identity-aware, secret-free engineer source manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .source_manifest import PERMISSION_STATUSES


MACHINE_STATUSES = {"NATIVE_RSS", "OFFICIAL_API", "PENDING_REVIEW", "NONE_FOUND"}
OWNERSHIP = {"PERSONAL", "EMPLOYER", "COMMUNITY", "UNKNOWN"}
SOURCE_KINDS = {"PERSONAL_BLOG", "PERSONAL_SITE", "NEWSLETTER", "EMPLOYER_BLOG", "GITHUB", "PAPER", "PODCAST", "CONFERENCE"}
SECRET_RE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]|://[^/\s:@]+:[^/\s@]+@")
REQUIRED_FIELDS = {
    "source_id", "person_name", "person_id", "themes", "source_name", "canonical_url",
    "endpoint_or_scope", "source_ownership", "source_kind", "organization_at_publication",
    "machine_readable_status", "permission_status", "retention_mode", "cadence",
    "artifact_types", "fixture_plan", "fallback", "correlation_group", "enabled",
}


class EngineerSourceManifestError(ValueError):
    """The engineer source manifest is incomplete, unsafe, or inconsistent."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineerSourceManifestError("engineer source manifest could not be read") from exc
    validate_manifest(payload)
    return dict(payload)


def validate_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("sources"), list):
        raise EngineerSourceManifestError("engineer source manifest requires schema_version 1 and sources")
    sources = payload["sources"]
    if len(sources) < 12:
        raise EngineerSourceManifestError("engineer source manifest requires at least twelve people")
    people: set[str] = set()
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise EngineerSourceManifestError(f"source {index} must be an object")
        missing = REQUIRED_FIELDS - set(source)
        if missing:
            raise EngineerSourceManifestError(f"source {index} missing: {', '.join(sorted(missing))}")
        person_id = source["person_id"]
        source_id = source["source_id"]
        if not isinstance(person_id, str) or not person_id.strip() or person_id in people:
            raise EngineerSourceManifestError(f"source {index} has an invalid or duplicate person_id")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in source_ids:
            raise EngineerSourceManifestError(f"source {index} has an invalid or duplicate source_id")
        people.add(person_id)
        source_ids.add(source_id)
        for field in ("person_name", "source_name", "canonical_url", "endpoint_or_scope", "organization_at_publication", "retention_mode", "cadence", "fixture_plan", "fallback", "correlation_group"):
            if not isinstance(source[field], str) or not source[field].strip():
                raise EngineerSourceManifestError(f"source {source_id} requires non-empty {field}")
        for field in ("themes", "artifact_types"):
            if not isinstance(source[field], list) or not source[field] or any(not isinstance(item, str) or not item.strip() for item in source[field]):
                raise EngineerSourceManifestError(f"source {source_id} requires a non-empty {field} list")
        if source["source_ownership"] not in OWNERSHIP:
            raise EngineerSourceManifestError(f"source {source_id} has invalid source_ownership")
        if source["source_kind"] not in SOURCE_KINDS:
            raise EngineerSourceManifestError(f"source {source_id} has invalid source_kind")
        if source["machine_readable_status"] not in MACHINE_STATUSES:
            raise EngineerSourceManifestError(f"source {source_id} has invalid machine_readable_status")
        if source["permission_status"] not in PERMISSION_STATUSES:
            raise EngineerSourceManifestError(f"source {source_id} has invalid permission_status")
        if source["enabled"] is not False:
            raise EngineerSourceManifestError(f"source {source_id} must remain disabled pending review")
        for field in ("canonical_url", "endpoint_or_scope"):
            if not source[field].lower().startswith(("http://", "https://")):
                raise EngineerSourceManifestError(f"source {source_id} {field} must be HTTP(S)")
        if SECRET_RE.search(json.dumps(source, sort_keys=True)):
            raise EngineerSourceManifestError(f"source {source_id} contains a credential-like value")
