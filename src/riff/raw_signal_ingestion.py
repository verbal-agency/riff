"""Fixture-safe ingestion for cross-domain raw signals (G38).

The existing evidence ledger remains the system of record.  This adapter adds
structured signal metadata without inventing a new evidence store or asking a
model to summarize every source at collection time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence import EvidenceSubmission, SourceType
from .evidence_repository import EvidenceRepository

SCHEMA_VERSION = 1
POLICY_VERSION = "raw-signal-ingestion-policy-v1"
SIGNAL_CLASSES = {
    "INCIDENT_REPORT", "POSTMORTEM", "TRAJECTORY_OBSERVABILITY",
    "RELIABILITY_RESEARCH", "SCIENTIFIC_PAPER", "PAPER_CODE",
    "DATASET", "BENCHMARK", "ENGINEERING_BLOG", "CHANGELOG",
    "GITHUB_DISCUSSION", "GITHUB_ISSUE", "GITHUB_PR",
}
EVIDENCE_ROLES = {"PRIMARY_EVIDENCE", "SECONDARY_SYNTHESIS", "USER_LEAD"}


class RawSignalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RawSignal:
    signal_id: str
    source_id: str
    source_type: SourceType
    signal_class: str
    title: str
    canonical_url: str
    canonical_root: str | None
    content: str
    published_at: datetime | None
    author: str | None
    organization: str | None
    linked_artifacts: tuple[str, ...]
    version: str | None
    commit: str | None
    correlation_group: str | None
    evidence_role: str
    equivalent_of: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RawSignal":
        required = ("signal_id", "source_id", "source_type", "signal_class", "title", "canonical_url", "content", "evidence_role")
        missing = [field for field in required if not str(value.get(field, "")).strip()]
        if missing:
            raise RawSignalError("raw signal missing: " + ", ".join(missing))
        signal_class = str(value["signal_class"]).strip().upper()
        if signal_class not in SIGNAL_CLASSES:
            raise RawSignalError(f"unsupported signal_class: {signal_class}")
        role = str(value["evidence_role"]).strip().upper()
        if role not in EVIDENCE_ROLES:
            raise RawSignalError(f"unsupported evidence_role: {role}")
        try:
            source_type = SourceType(str(value["source_type"]).strip().upper())
        except ValueError as exc:
            raise RawSignalError(f"unsupported source_type: {value['source_type']}") from exc
        published = value.get("published_at")
        published_at = None
        if published:
            try:
                published_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            except ValueError as exc:
                raise RawSignalError("published_at must be ISO-8601") from exc
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        artifacts = value.get("linked_artifacts", [])
        if not isinstance(artifacts, list) or any(not str(item).strip() for item in artifacts):
            raise RawSignalError("linked_artifacts must be a list of non-empty strings")
        return cls(
            signal_id=str(value["signal_id"]).strip(), source_id=str(value["source_id"]).strip(),
            source_type=source_type, signal_class=signal_class, title=str(value["title"]).strip(),
            canonical_url=str(value["canonical_url"]).strip(), canonical_root=str(value.get("canonical_root") or "").strip() or None,
            content=str(value["content"]), published_at=published_at,
            author=str(value.get("author") or "").strip() or None, organization=str(value.get("organization") or "").strip() or None,
            linked_artifacts=tuple(str(item).strip() for item in artifacts), version=str(value.get("version") or "").strip() or None,
            commit=str(value.get("commit") or "").strip() or None, correlation_group=str(value.get("correlation_group") or "").strip() or None,
            evidence_role=role, equivalent_of=str(value.get("equivalent_of") or "").strip() or None,
        )


def load_fixture(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawSignalError(f"raw signal fixture could not be read: {exc}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("signals"), list):
        raise RawSignalError("raw signal fixture requires schema_version 1 and signals")
    if len(payload["signals"]) > 50:
        raise RawSignalError("raw signal fixture is limited to 50 signals")
    signals = [RawSignal.from_mapping(item) for item in payload["signals"] if isinstance(item, Mapping)]
    if len(signals) != len(payload["signals"]):
        raise RawSignalError("each signal must be an object")
    ids = [item.signal_id for item in signals]
    if len(set(ids)) != len(ids):
        raise RawSignalError("signal_id values must be unique")
    return {"schema_version": SCHEMA_VERSION, "fixture_id": str(payload.get("fixture_id", "raw-signals")), "signals": signals}


def load_source_manifest(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawSignalError(f"raw signal source manifest could not be read: {exc}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("sources"), list):
        raise RawSignalError("raw signal source manifest requires schema_version 1 and sources")
    ids: set[str] = set()
    for entry in payload["sources"]:
        if not isinstance(entry, Mapping):
            raise RawSignalError("each raw signal source must be an object")
        for field in ("source_id", "name", "endpoint", "signal_class", "source_type", "permission_status"):
            if not str(entry.get(field, "")).strip():
                raise RawSignalError(f"raw signal source missing {field}")
        source_id = str(entry["source_id"]).strip()
        if source_id in ids:
            raise RawSignalError(f"duplicate raw signal source_id: {source_id}")
        ids.add(source_id)
        if str(entry["signal_class"]).strip().upper() not in SIGNAL_CLASSES:
            raise RawSignalError(f"unsupported signal_class: {entry['signal_class']}")
        if str(entry["source_type"]).strip().upper() not in {item.value for item in SourceType}:
            raise RawSignalError(f"unsupported source_type: {entry['source_type']}")
        if not str(entry["endpoint"]).strip().lower().startswith(("http://", "https://")):
            raise RawSignalError(f"source {source_id} endpoint must be HTTP(S)")
    return {"schema_version": SCHEMA_VERSION, "sources": [dict(entry) for entry in payload["sources"]]}


class RawSignalIngestionRunner:
    def __init__(self, evidence: EvidenceRepository):
        self.evidence = evidence

    def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        signals = payload.get("signals", [])
        classes: dict[str, int] = {}
        roles: dict[str, int] = {}
        for signal in signals:
            classes[signal.signal_class] = classes.get(signal.signal_class, 0) + 1
            roles[signal.evidence_role] = roles.get(signal.evidence_role, 0) + 1
        return {"schema_version": SCHEMA_VERSION, "fixture_id": payload.get("fixture_id"), "signal_count": len(signals), "classes": dict(sorted(classes.items())), "evidence_roles": dict(sorted(roles.items())), "policy_version": POLICY_VERSION}

    def ingest(self, payload: Mapping[str, Any], *, fixture_mode: bool = True, owner: str = "raw-signal-fixture") -> dict[str, Any]:
        signals: Sequence[RawSignal] = payload.get("signals", [])
        stored = duplicates = 0
        results: list[dict[str, Any]] = []
        for signal in signals:
            self.evidence.create_source(signal.source_type, signal.source_id, canonical_root=signal.canonical_root, enabled=False, source_id=signal.source_id)
            role_uncertainty = [] if signal.evidence_role == "PRIMARY_EVIDENCE" else ["secondary_or_user_supplied_signal_requires_source_validation"]
            metadata = {
                "adapter": "raw_signal_fixture" if fixture_mode else "raw_signal",
                "signal_id": signal.signal_id, "signal_class": signal.signal_class,
                "evidence_role": signal.evidence_role, "author": signal.author,
                "organization": signal.organization, "canonical_root": signal.canonical_root,
                "linked_artifacts": list(signal.linked_artifacts), "version": signal.version,
                "commit": signal.commit, "correlation_group": signal.correlation_group,
                "uncertainty": role_uncertainty, "policy_version": POLICY_VERSION,
                "fixture": fixture_mode,
            }
            result = self.evidence.ingest(EvidenceSubmission(
                source_id=signal.source_id, canonical_url=signal.canonical_url,
                native_id=signal.signal_id, title=signal.title, published_at=signal.published_at,
                raw_content=signal.content, retrieval_metadata=metadata,
                data_origin="FIXTURE" if fixture_mode else "LIVE", origin_owner=owner if fixture_mode else None,
                origin_policy_version=POLICY_VERSION,
            ))
            stored += int(result.created); duplicates += int(not result.created)
            results.append({"signal_id": signal.signal_id, "evidence_id": result.evidence_id, "source_item_id": result.source_item_id, "created": result.created, "evidence_role": signal.evidence_role, "uncertainty": role_uncertainty})
        return {"fixture_id": payload.get("fixture_id"), "stored": stored, "duplicates": duplicates, "signal_count": len(signals), "results": results, "policy_version": POLICY_VERSION}
