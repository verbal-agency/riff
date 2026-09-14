"""Fail-closed selection and projection for engineer-authored RSS sources."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .engineer_sources import load_manifest as load_engineer_manifest
from .source_manifest import PERMISSION_STATUSES


DECISIONS = {"DRY_RUN", "PENDING", "ENABLE", "BLOCK"}
SECRET_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]|://[^/\s:@]+:[^/\s@]+@"
)
REQUIRED_FIELDS = {
    "selection_id", "engineer_source_id", "registry_source_id", "endpoint", "source_root",
    "source_ownership", "person_id", "person_name", "organization_at_publication",
    "correlation_group", "permission_status", "retention_mode", "reviewed_at", "reviewed_by",
    "collection_decision", "fixture_plan", "enabled",
}


class EngineerRssSelectionError(ValueError):
    """A selection is incomplete, unsafe, or not eligible for promotion."""


def load_selection_manifest(path: str | Path, *, engineer_manifest_path: str | Path = "config/engineer_sources.json") -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineerRssSelectionError("engineer RSS selection manifest could not be read") from exc
    engineers = load_engineer_manifest(engineer_manifest_path)
    validate_selection_manifest(payload, engineers)
    return dict(payload)


def validate_selection_manifest(payload: Mapping[str, Any], engineers: Mapping[str, Any] | None = None) -> None:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("selections"), list):
        raise EngineerRssSelectionError("selection manifest requires schema_version 1 and selections")
    selections = payload["selections"]
    if len(selections) < 3:
        raise EngineerRssSelectionError("selection manifest requires at least three engineer sources")
    engineer_by_id = {}
    if engineers is not None:
        engineer_by_id = {item["source_id"]: item for item in engineers.get("sources", [])}
    selection_ids: set[str] = set()
    registry_ids: set[str] = set()
    endpoints: set[str] = set()
    for index, selection in enumerate(selections):
        if not isinstance(selection, Mapping):
            raise EngineerRssSelectionError(f"selection {index} must be an object")
        missing = REQUIRED_FIELDS - set(selection)
        if missing:
            raise EngineerRssSelectionError(f"selection {index} missing: {', '.join(sorted(missing))}")
        selection_id = selection["selection_id"]
        registry_id = selection["registry_source_id"]
        endpoint = selection["endpoint"]
        if not isinstance(selection_id, str) or not selection_id.strip() or selection_id in selection_ids:
            raise EngineerRssSelectionError(f"selection {index} has an invalid or duplicate selection_id")
        if not isinstance(registry_id, str) or not registry_id.strip() or registry_id in registry_ids:
            raise EngineerRssSelectionError(f"selection {selection_id} has an invalid or duplicate registry_source_id")
        if not isinstance(endpoint, str) or not endpoint.lower().startswith(("http://", "https://")):
            raise EngineerRssSelectionError(f"selection {selection_id} endpoint must be HTTP(S)")
        normalized_endpoint = endpoint.rstrip("/").lower()
        if normalized_endpoint in endpoints:
            raise EngineerRssSelectionError(f"selection {selection_id} duplicates an endpoint")
        selection_ids.add(selection_id)
        registry_ids.add(registry_id)
        endpoints.add(normalized_endpoint)
        for field in ("source_root", "source_ownership", "person_id", "person_name", "organization_at_publication", "correlation_group", "retention_mode", "fixture_plan"):
            if not isinstance(selection[field], str) or not selection[field].strip():
                raise EngineerRssSelectionError(f"selection {selection_id} requires non-empty {field}")
        if not selection["source_root"].lower().startswith(("http://", "https://")):
            raise EngineerRssSelectionError(f"selection {selection_id} source_root must be HTTP(S)")
        if selection["collection_decision"] not in DECISIONS:
            raise EngineerRssSelectionError(f"selection {selection_id} has an invalid collection_decision")
        if selection["permission_status"] not in PERMISSION_STATUSES:
            raise EngineerRssSelectionError(f"selection {selection_id} has an invalid permission_status")
        if not isinstance(selection["enabled"], bool):
            raise EngineerRssSelectionError(f"selection {selection_id} enabled must be boolean")
        if selection["enabled"] and selection["collection_decision"] != "ENABLE":
            raise EngineerRssSelectionError(f"selection {selection_id} cannot enable a non-ENABLE decision")
        if selection["collection_decision"] == "ENABLE":
            if selection["permission_status"] not in {"CONFIRMED", "USER_PROVIDED"}:
                raise EngineerRssSelectionError(f"selection {selection_id} requires confirmed permission to enable")
            if not isinstance(selection["reviewed_at"], str) or not selection["reviewed_at"].strip():
                raise EngineerRssSelectionError(f"selection {selection_id} requires reviewed_at to enable")
            if not isinstance(selection["reviewed_by"], str) or not selection["reviewed_by"].strip():
                raise EngineerRssSelectionError(f"selection {selection_id} requires reviewed_by to enable")
        engineer = engineer_by_id.get(selection["engineer_source_id"])
        if engineers is not None and engineer is None:
            raise EngineerRssSelectionError(f"selection {selection_id} references an unknown engineer_source_id")
        if engineer is not None:
            if engineer.get("machine_readable_status") != "NATIVE_RSS":
                raise EngineerRssSelectionError(f"selection {selection_id} does not reference a native RSS source")
            if selection["person_id"] != engineer.get("person_id") or selection["person_name"] != engineer.get("person_name"):
                raise EngineerRssSelectionError(f"selection {selection_id} person identity does not match the roster")
            if selection["source_ownership"] != engineer.get("source_ownership"):
                raise EngineerRssSelectionError(f"selection {selection_id} ownership does not match the roster")
        if SECRET_RE.search(json.dumps(selection, sort_keys=True)):
            raise EngineerRssSelectionError(f"selection {selection_id} contains a credential-like value")


def selection_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return operator-visible statuses without mutating a registry."""

    validate_selection_manifest(payload)
    result = []
    for selection in payload["selections"]:
        decision = selection["collection_decision"]
        if decision == "ENABLE" and selection["enabled"]:
            status = "eligible"
        elif decision == "DRY_RUN":
            status = "dry_run"
        elif decision == "BLOCK":
            status = "blocked"
        else:
            status = "pending"
        result.append({"selection_id": selection["selection_id"], "registry_source_id": selection["registry_source_id"], "status": status})
    return {"schema_version": payload["schema_version"], "selections": result}


def project_registries(
    payload: Mapping[str, Any],
    technical_registry: Mapping[str, Any],
    ingestion_manifest: Mapping[str, Any],
    *,
    selection_ids: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project only explicitly enabled selections into both source registries."""

    validate_selection_manifest(payload)
    selected = payload["selections"]
    if selection_ids is not None:
        wanted = set(selection_ids)
        unknown = wanted - {item["selection_id"] for item in selected}
        if unknown:
            raise EngineerRssSelectionError(f"unknown selection_id(s): {', '.join(sorted(unknown))}")
        selected = [item for item in selected if item["selection_id"] in wanted]
    if not selected:
        raise EngineerRssSelectionError("no engineer RSS selections were requested")
    blocked = [item["selection_id"] for item in selected if item["collection_decision"] != "ENABLE" or not item["enabled"]]
    if blocked:
        raise EngineerRssSelectionError(f"selections are not eligible for projection: {', '.join(blocked)}")

    technical = copy.deepcopy(dict(technical_registry))
    ingestion = copy.deepcopy(dict(ingestion_manifest))
    technical_sources = technical.get("sources")
    ingestion_sources = ingestion.get("sources")
    rss_inventory = ingestion.get("rss_inventory")
    if not isinstance(technical_sources, list) or not isinstance(ingestion_sources, list) or not isinstance(rss_inventory, list):
        raise EngineerRssSelectionError("both registries require source lists and ingestion rss_inventory")
    for selection in selected:
        technical_entry, ingestion_entry, rss_entry = _entries(selection)
        _upsert_by_id_and_endpoint(technical_sources, technical_entry)
        _upsert_by_id_and_endpoint(ingestion_sources, ingestion_entry, endpoint_field="endpoint_or_scope")
        _upsert_by_id_and_endpoint(rss_inventory, rss_entry, endpoint_field="endpoint")
    return technical, ingestion


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _entries(selection: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_id = selection["registry_source_id"]
    metadata = {
        "engineer_source_id": selection["engineer_source_id"],
        "person_id": selection["person_id"],
        "person_name": selection["person_name"],
        "source_ownership": selection["source_ownership"],
        "organization_at_publication": selection["organization_at_publication"],
        "source_root": selection["source_root"],
        "correlation_group": selection["correlation_group"],
        "attribution_policy": "SOURCE_OWNED_PERSONAL" if selection["source_ownership"] == "PERSONAL" else "REQUIRE_AUTHOR_MATCH",
    }
    technical = {
        "source_id": source_id,
        "name": f"{selection['person_name']} — engineer-authored RSS",
        "source_type": "TECHNICAL_WRITING",
        "endpoint": selection["endpoint"],
        "enabled": bool(selection["enabled"]),
        "config_version": 3,
        "cursor_kind": "updated_at",
        "source_root": selection["source_root"],
        "source_class": "ENGINEER_AUTHORED",
        "feed_format": "RSS_OR_ATOM",
        "permission_status": selection["permission_status"],
        "retention_mode": selection["retention_mode"],
        "cadence": selection.get("cadence", "irregular"),
        "artifact_types": selection.get("artifact_types", ["blog_entry"]),
        "fixture_plan": selection["fixture_plan"],
        "rate_limit_policy": "One bounded feed request per scheduled run; honor retry-after.",
        "fallback": "Remain disabled and retain canonical URL only if terms or attribution are unresolved.",
        **metadata,
    }
    ingestion = {
        "source_id": source_id,
        "name": technical["name"],
        "source_type": "TECHNICAL_WRITING",
        "endpoint_or_scope": selection["endpoint"],
        "access_method": "RSS/Atom source-owned feed",
        "permission_status": selection["permission_status"],
        "retention_mode": selection["retention_mode"],
        "cadence": technical["cadence"],
        "expected_artifacts": technical["artifact_types"],
        "identity_fields": ["canonical_url", "published_at", "title", "author", "engineer_source_id", "correlation_group"],
        "fixture_plan": selection["fixture_plan"],
        "rate_limit_policy": technical["rate_limit_policy"],
        "fallback": technical["fallback"],
        "enabled": technical["enabled"],
        **metadata,
    }
    rss = {
        "source_id": source_id,
        "name": technical["name"],
        "endpoint": selection["endpoint"],
        "owner": selection["person_name"],
        "source_root": selection["source_root"],
        "artifact_class": "ENGINEER_AUTHORED",
        "permission_status": selection["permission_status"],
        "enabled": technical["enabled"],
        **metadata,
    }
    return technical, ingestion, rss


def _upsert_by_id_and_endpoint(entries: list[dict[str, Any]], new_entry: dict[str, Any], *, endpoint_field: str = "endpoint") -> None:
    source_id = new_entry["source_id"]
    endpoint = new_entry[endpoint_field].rstrip("/").lower()
    for index, existing in enumerate(entries):
        if existing.get("source_id") == source_id:
            if existing.get(endpoint_field, "").rstrip("/").lower() not in {"", endpoint}:
                raise EngineerRssSelectionError(f"{source_id} changes an existing endpoint")
            entries[index] = {**existing, **new_entry}
            return
        if existing.get(endpoint_field, "").rstrip("/").lower() == endpoint:
            raise EngineerRssSelectionError(f"{source_id} duplicates an existing endpoint")
    entries.append(new_entry)
