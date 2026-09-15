"""Evidence-backed, bounded understanding of user-owned GitHub projects (G26)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection


PARSER_VERSION = "github-project-map-v1"
POLICY_VERSION = "github-project-map-policy-v1"
_STATUSES = {"ACTIVE", "ARCHIVED"}


class ProjectMapError(ValueError):
    """Raised when a project inventory or bounded snapshot is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectInventory:
    project_id: str
    provider_repository_id: str
    display_name: str
    purpose: str | None
    status: str
    visibility: str
    review_status: str
    reviewed_by: str
    reviewed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    snapshot_id: str
    project_id: str
    version: int
    retrieved_at: datetime
    parser_version: str
    policy_version: str
    input_hash: str
    previous_snapshot_id: str | None
    source_evidence_ids: tuple[str, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_evidence_ids"] = list(self.source_evidence_ids)
        return value


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except json.JSONDecodeError:
            return default
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim(
    value: Any,
    *,
    kind: str,
    evidence_ids: list[str],
    confidence: float,
    status: str,
    receipt_ids: list[str] | None = None,
    mapping_ids: list[str] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    """Create the one shape used for every inspectable summary claim."""

    return {
        "kind": kind,
        "value": value,
        "evidence_ids": sorted(set(evidence_ids)),
        "receipt_ids": sorted(set(receipt_ids or [])),
        "mapping_ids": sorted(set(mapping_ids or [])),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "status": status,
        **({"rationale": rationale} if rationale else {}),
        "parser_version": PARSER_VERSION,
        "policy_version": POLICY_VERSION,
    }


class ProjectMapRepository:
    """Persist user-approved project identities and immutable map snapshots."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def onboard(
        self,
        provider_repository_id: str,
        *,
        display_name: str | None = None,
        purpose: str | None = None,
        reviewed_by: str = "user",
        project_id: str | None = None,
    ) -> ProjectInventory:
        if purpose is not None and not isinstance(purpose, str):
            raise ProjectMapError("purpose must be a string")
        provider_repository_id = _text(provider_repository_id)
        reviewed_by = _text(reviewed_by)
        if not provider_repository_id or not reviewed_by:
            raise ProjectMapError("provider_repository_id and reviewed_by are required")
        with connection(self.database_url) as conn:
            repository = conn.execute(
                "SELECT provider_repository_id, name, metadata FROM github_repositories "
                "WHERE provider_repository_id = %s",
                (provider_repository_id,),
            ).fetchone()
            if repository is None:
                raise ProjectMapError("GitHub repository is not ingested; onboard it through G03 first")
            metadata = _json(repository[2], {})
            visibility = _text(metadata.get("visibility")) if isinstance(metadata, Mapping) else ""
            if visibility and visibility.lower() != "public":
                raise ProjectMapError("only public GitHub repositories may be onboarded")
            name = _text(display_name) or _text(repository[1])
            if not name:
                raise ProjectMapError("display_name is required")
            existing = conn.execute(
                "SELECT project_id FROM github_project_inventory WHERE provider_repository_id = %s",
                (provider_repository_id,),
            ).fetchone()
            actual_project_id = _text(existing[0]) if existing else (project_id or str(uuid.uuid4()))
            reviewed_at = _now()
            conn.execute(
                """
                INSERT INTO github_project_inventory
                (project_id, provider_repository_id, display_name, purpose, status,
                 visibility, review_status, reviewed_by, reviewed_at, archived_at)
                VALUES (%s, %s, %s, %s, 'ACTIVE', 'PUBLIC', 'APPROVED', %s, %s, NULL)
                ON CONFLICT (provider_repository_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    purpose = EXCLUDED.purpose,
                    status = 'ACTIVE',
                    visibility = 'PUBLIC',
                    review_status = 'APPROVED',
                    reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at,
                    updated_at = now(),
                    archived_at = NULL
                """,
                (actual_project_id, provider_repository_id, name, purpose.strip() if purpose and purpose.strip() else None, reviewed_by, reviewed_at),
            )
        return self.get(actual_project_id)

    def archive(self, project_id: str, *, reviewed_by: str = "user") -> ProjectInventory:
        if not _text(project_id) or not _text(reviewed_by):
            raise ProjectMapError("project_id and reviewed_by are required")
        with connection(self.database_url) as conn:
            result = conn.execute(
                "UPDATE github_project_inventory SET status = 'ARCHIVED', review_status = 'ARCHIVED', "
                "reviewed_by = %s, reviewed_at = %s, updated_at = now(), archived_at = %s "
                "WHERE project_id = %s",
                (reviewed_by.strip(), _now(), _now(), project_id),
            )
            if result.rowcount != 1:
                raise ProjectMapError("project not found")
        return self.get(project_id)

    def get(self, project_id: str) -> ProjectInventory:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT project_id, provider_repository_id, display_name, purpose, status, visibility, "
                "review_status, reviewed_by, reviewed_at FROM github_project_inventory WHERE project_id = %s",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ProjectMapError("project not found")
        return ProjectInventory(
            _text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]) or None,
            _text(row[4]), _text(row[5]), _text(row[6]), _text(row[7]), row[8],
        )

    def refresh(
        self,
        project_id: str,
        *,
        retrieved_at: datetime | None = None,
        parser_version: str = PARSER_VERSION,
        policy_version: str = POLICY_VERSION,
    ) -> ProjectSnapshot:
        inventory = self.get(project_id)
        if inventory.status != "ACTIVE":
            raise ProjectMapError("archived project cannot be refreshed")
        if not _text(parser_version) or not _text(policy_version):
            raise ProjectMapError("parser_version and policy_version are required")
        retrieved_at = retrieved_at or _now()
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
        with connection(self.database_url) as conn:
            repo = conn.execute(
                "SELECT provider_repository_id, owner_login, name, canonical_url, stars, metadata "
                "FROM github_repositories WHERE provider_repository_id = %s",
                (inventory.provider_repository_id,),
            ).fetchone()
            if repo is None:
                raise ProjectMapError("backing GitHub repository not found")
            rows = conn.execute(
                """
                SELECT ga.evidence_id, ga.provider_artifact_id, ga.artifact_type,
                       ga.canonical_url, ga.author_login, ga.observed_at, ga.metadata,
                       si.title, e.raw_content, e.content_hash
                FROM github_artifacts ga
                JOIN evidence_versions e ON e.evidence_id = ga.evidence_id
                JOIN source_items si ON si.source_item_id = e.source_item_id
                WHERE ga.provider_repository_id = %s
                ORDER BY ga.observed_at DESC, ga.provider_artifact_id DESC
                LIMIT 200
                """,
                (inventory.provider_repository_id,),
            ).fetchall()
            artifacts = [_artifact_row(row) for row in rows]
            evidence_ids = [item["evidence_id"] for item in artifacts]
            mappings = self._mappings(conn, evidence_ids)
            summary = _build_summary(inventory, repo, artifacts, mappings)
            fingerprint_payload = {
                "provider_repository_id": inventory.provider_repository_id,
                "parser_version": parser_version,
                "policy_version": policy_version,
                "repository": [_json(repo[5], {}), _text(repo[4])],
                "artifacts": [
                    {key: (item[key].isoformat() if key == "observed_at" and item[key] else item[key]) for key in ("evidence_id", "provider_artifact_id", "artifact_type", "observed_at", "content_hash", "metadata")}
                    for item in artifacts
                ],
                "summary": summary,
            }
            input_hash = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, default=str).encode()).hexdigest()
            existing = conn.execute(
                "SELECT snapshot_id FROM github_project_snapshots WHERE project_id = %s AND input_hash = %s",
                (project_id, input_hash),
            ).fetchone()
            if existing:
                return self.get_snapshot(_text(existing[0]))
            prior = conn.execute(
                "SELECT snapshot_id, version FROM github_project_snapshots WHERE project_id = %s ORDER BY version DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            snapshot_id = str(uuid.uuid4())
            version = int(prior[1]) + 1 if prior else 1
            conn.execute(
                """
                INSERT INTO github_project_snapshots
                (snapshot_id, project_id, version, retrieved_at, parser_version,
                 policy_version, input_hash, previous_snapshot_id,
                 source_evidence_ids, summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (snapshot_id, project_id, version, retrieved_at, parser_version, policy_version, input_hash,
                 _text(prior[0]) if prior else None, Jsonb(evidence_ids), Jsonb(summary)),
            )
        return self.get_snapshot(snapshot_id)

    def _mappings(self, conn, evidence_ids: list[str]) -> list[dict[str, Any]]:
        if not evidence_ids:
            return []
        rows = conn.execute(
            """
            SELECT m.mapping_id, m.receipt_id, r.evidence_id, m.entity_type,
                   m.entity_id, m.confidence, m.status, m.rationale,
                   c.name, t.name
            FROM capability_mappings m
            JOIN evidence_receipts r ON r.receipt_id = m.receipt_id
            LEFT JOIN capabilities c ON m.entity_type = 'CAPABILITY' AND c.capability_id = m.entity_id
            LEFT JOIN technologies t ON m.entity_type = 'TECHNOLOGY' AND t.technology_id = m.entity_id
            WHERE r.evidence_id = ANY(%s) AND m.status IN ('PROPOSED', 'ACCEPTED')
            ORDER BY m.created_at, m.mapping_id
            """,
            (evidence_ids,),
        ).fetchall()
        return [
            {
                "mapping_id": _text(row[0]), "receipt_id": _text(row[1]), "evidence_id": _text(row[2]),
                "entity_type": _text(row[3]), "entity_id": _text(row[4]) or None,
                "confidence": float(row[5]), "status": _text(row[6]), "rationale": _text(row[7]),
                "name": _text(row[8] if row[3] == "CAPABILITY" else row[9]),
            }
            for row in rows
        ]

    def get_snapshot(self, snapshot_id: str) -> ProjectSnapshot:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT snapshot_id, project_id, version, retrieved_at, parser_version, policy_version, "
                "input_hash, previous_snapshot_id, source_evidence_ids, summary "
                "FROM github_project_snapshots WHERE snapshot_id = %s",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise ProjectMapError("snapshot not found")
        return ProjectSnapshot(
            _text(row[0]), _text(row[1]), int(row[2]), row[3], _text(row[4]), _text(row[5]),
            _text(row[6]), _text(row[7]) or None,
            tuple(_text(item) for item in _json(row[8], [])), dict(_json(row[9], {})),
        )

    def latest_snapshot(self, project_id: str) -> ProjectSnapshot | None:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT snapshot_id FROM github_project_snapshots WHERE project_id = %s ORDER BY version DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return self.get_snapshot(_text(row[0])) if row else None

    def inspect(self, project_id: str) -> dict[str, Any]:
        inventory = self.get(project_id)
        with connection(self.database_url) as conn:
            aliases = conn.execute(
                "SELECT canonical_url FROM github_repository_aliases WHERE provider_repository_id = %s ORDER BY canonical_url",
                (inventory.provider_repository_id,),
            ).fetchall()
            history = conn.execute(
                "SELECT snapshot_id, version, retrieved_at, parser_version, policy_version, input_hash "
                "FROM github_project_snapshots WHERE project_id = %s ORDER BY version",
                (project_id,),
            ).fetchall()
        latest = self.latest_snapshot(project_id)
        return {
            "project": inventory.to_dict(),
            "repository_aliases": [_text(row[0]) for row in aliases],
            "latest_snapshot": latest.to_dict() if latest else None,
            "snapshot_history": [
                {"snapshot_id": _text(row[0]), "version": int(row[1]), "retrieved_at": row[2],
                 "parser_version": _text(row[3]), "policy_version": _text(row[4]), "input_hash": _text(row[5])}
                for row in history
            ],
        }


def _artifact_row(row: tuple[Any, ...]) -> dict[str, Any]:
    content = _text(row[8])
    metadata = _json(row[6], {})
    return {
        "evidence_id": _text(row[0]), "provider_artifact_id": _text(row[1]),
        "artifact_type": _text(row[2]), "canonical_url": _text(row[3]),
        "author_login": _text(row[4]) or None, "observed_at": row[5],
        "metadata": metadata if isinstance(metadata, Mapping) else {}, "title": _text(row[7]) or None,
        "content": content, "content_hash": _text(row[9]),
    }


def _build_summary(inventory: ProjectInventory, repo: tuple[Any, ...], artifacts: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> dict[str, Any]:
    repo_metadata = _json(repo[5], {})
    repo_evidence = [item for item in artifacts if item["artifact_type"] == "REPOSITORY"]
    readmes = [item for item in artifacts if item["artifact_type"] == "README_CHANGE"]
    all_ids = [item["evidence_id"] for item in artifacts]
    description = _text(repo_metadata.get("description")) if isinstance(repo_metadata, Mapping) else ""
    description_evidence = [item["evidence_id"] for item in repo_evidence]
    readme_text = next((item["content"] for item in readmes if item["content"]), "")
    first_line = next((line.strip(" #-") for line in readme_text.splitlines() if line.strip()), "")
    purpose = inventory.purpose or description or first_line or None
    purpose_evidence = description_evidence if inventory.purpose is None and description else ([item["evidence_id"] for item in readmes] if inventory.purpose is None else [])
    claims: list[dict[str, Any]] = []
    if purpose:
        claims.append(_claim(purpose, kind="purpose", evidence_ids=purpose_evidence or all_ids, confidence=0.95 if description else 0.70, status="OBSERVED" if description else "INFERRED"))
    else:
        claims.append(_claim(None, kind="purpose", evidence_ids=all_ids, confidence=0.0, status="UNKNOWN", rationale="No repository description or bounded README purpose was available"))

    capabilities: list[dict[str, Any]] = []
    technologies: list[dict[str, Any]] = []
    for mapping in mappings:
        if not mapping["name"]:
            continue
        target = capabilities if mapping["entity_type"] == "CAPABILITY" else technologies
        claim = _claim(mapping["name"], kind=mapping["entity_type"].lower(), evidence_ids=[mapping["evidence_id"]], confidence=mapping["confidence"], status=mapping["status"], receipt_ids=[mapping["receipt_id"]], mapping_ids=[mapping["mapping_id"]], rationale=mapping["rationale"])
        if not any(item["value"] == claim["value"] for item in target):
            target.append(claim)
    # G03 already bounds stored bodies; keep this parser defensive if called
    # with a malformed or oversized fixture directly.
    corpus = " ".join([_text(repo_metadata.get("description")), *(item["title"] or "" for item in artifacts), *(item["content"][:20_000] for item in artifacts)]).lower()
    patterns = {
        "python": r"\bpython\b", "postgres": r"\bpostgres(?:ql)?\b", "docker": r"\bdocker\b",
        "fastapi": r"\bfastapi\b", "temporal": r"\btemporal\b", "langgraph": r"\blanggraph\b",
        "github actions": r"github[ /_-]+actions|\.github/workflows",
    }
    mapped_tech_names = {str(item["value"]).lower() for item in technologies}
    for name, pattern in patterns.items():
        if name not in mapped_tech_names and re.search(pattern, corpus):
            technologies.append(_claim(name, kind="technology", evidence_ids=all_ids, confidence=0.55, status="INFERRED", rationale="Static bounded text match; no hands-on capability claim"))
    capability_patterns = {
        "durable execution": r"durab(?:le|ility)|checkpoint|replay|resume|workflow recovery",
        "agent orchestration": r"agent orchestration|agent runtime|workflow orchestration",
    }
    mapped_cap_names = {str(item["value"]).lower() for item in capabilities}
    for name, pattern in capability_patterns.items():
        if name not in mapped_cap_names and re.search(pattern, corpus):
            capabilities.append(_claim(name, kind="capability", evidence_ids=all_ids, confidence=0.50, status="INFERRED", rationale="Static bounded text match; requires receipt-backed normalization or user assessment"))

    releases = [item for item in artifacts if item["artifact_type"] == "RELEASE"]
    issues = [item for item in artifacts if item["artifact_type"] == "ISSUE"]
    open_issues = [item for item in issues if str(item["metadata"].get("state", "")).lower() == "open" or "open" in (item["title"] or "").lower()]
    last_observed = max((item["observed_at"] for item in artifacts), default=None)
    open_issue_count = len(open_issues)
    activity = [
        _claim(len(releases), kind="release_count", evidence_ids=[item["evidence_id"] for item in releases] or all_ids, confidence=1.0, status="OBSERVED"),
        _claim(len(issues), kind="issue_count", evidence_ids=[item["evidence_id"] for item in issues] or all_ids, confidence=1.0, status="OBSERVED"),
        _claim(last_observed.isoformat() if last_observed else None, kind="last_observed_at", evidence_ids=all_ids, confidence=1.0 if last_observed else 0.0, status="OBSERVED" if last_observed else "UNKNOWN"),
        _claim(repo[4], kind="stars", evidence_ids=description_evidence or all_ids, confidence=0.30, status="OBSERVED", rationale="Weak popularity metadata; not evidence of capability"),
    ]
    maturity = _claim(
        {"release_count": len(releases), "open_issue_count": open_issue_count, "has_recent_activity": bool(last_observed)},
        kind="maturity_indicators", evidence_ids=all_ids, confidence=0.85 if artifacts else 0.0,
        status="OBSERVED" if artifacts else "UNKNOWN",
        rationale="Counts are descriptive indicators, not a correctness or proficiency assessment",
    )
    seams = [
        _claim(item["title"] or item["canonical_url"], kind="open_issue", evidence_ids=[item["evidence_id"]], confidence=0.90, status="OBSERVED")
        for item in open_issues[:10]
    ]
    if not seams:
        seams.append(_claim(None, kind="open_issue", evidence_ids=all_ids, confidence=0.0, status="UNKNOWN", rationale="No open issues were present in the bounded snapshot"))
    unknowns = [
        _claim("ci_configuration", kind="unknown", evidence_ids=all_ids, confidence=0.0, status="UNKNOWN", rationale="G03 bounded artifacts do not include repository tree or workflow files"),
        _claim("implementation_depth", kind="unknown", evidence_ids=all_ids, confidence=0.0, status="UNKNOWN", rationale="Static metadata cannot establish code correctness or hands-on proficiency"),
    ]
    constraints = [
        _claim("public, bounded, static GitHub surfaces only", kind="constraint", evidence_ids=all_ids, confidence=1.0, status="OBSERVED", rationale="Project map never executes code or accesses private content"),
    ]
    return {
        "schema_version": 1,
        "project_id": inventory.project_id,
        "provider_repository_id": inventory.provider_repository_id,
        "display_name": inventory.display_name,
        "purpose": claims[0],
        "capabilities": capabilities,
        "technologies": technologies,
        "activity": activity,
        "maturity": maturity,
        "extension_seams": seams,
        "constraints": constraints,
        "unknowns": unknowns,
        "claims": claims + capabilities + technologies + activity + [maturity] + seams + constraints + unknowns,
        "evidence_index": [
            {"evidence_id": item["evidence_id"], "artifact_type": item["artifact_type"], "canonical_url": item["canonical_url"], "observed_at": item["observed_at"].isoformat() if item["observed_at"] else None}
            for item in artifacts
        ],
    }
