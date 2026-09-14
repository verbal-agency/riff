"""Reversible, receipt-backed capability and technology normalization."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from .db import connection
from .evidence import EvidenceValidationError
from .receipts import EvidenceReceipt, ReceiptRepository


SCHEMA_VERSION = 1
_MAPPING_STATUSES = {"PROPOSED", "ACCEPTED", "REJECTED", "SUPERSEDED"}
_ACTIONS = {"ACCEPT", "REJECT", "REMAP", "SPLIT", "UNDO"}


class NormalizationError(ValueError):
    """Raised when a normalization result or review operation is invalid."""


class Normalizer(Protocol):
    version: str

    def normalize(self, receipt: EvidenceReceipt) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class Capability:
    capability_id: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class Technology:
    technology_id: str
    name: str
    kind: str
    status: str


@dataclass(frozen=True, slots=True)
class CandidateMapping:
    mapping_id: str
    receipt_id: str
    candidate_text: str
    entity_type: str
    entity_id: str | None
    normalizer_version: str
    confidence: float
    status: str
    rationale: str


@dataclass(frozen=True, slots=True)
class CapabilityRelationship:
    relationship_id: str
    capability_id: str
    technology_id: str
    relationship_type: str
    confidence: float
    status: str
    mapping_id: str | None


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    mapping_id: str
    action: str
    actor: str
    reason: str
    previous_entity_id: str | None
    previous_status: str | None
    new_entity_id: str | None
    new_status: str | None


@dataclass(frozen=True, slots=True)
class NormalizationSummary:
    processed: int
    cached: int
    mappings: list[CandidateMapping]
    relationships: list[CapabilityRelationship]


@dataclass(frozen=True, slots=True)
class CapabilityInspection:
    capability: Capability
    concepts: list[str]
    patterns: list[str]
    technologies: list[Technology]
    mappings: list[CandidateMapping]
    decisions: list[ReviewDecision]


class CapabilityRepository:
    """Persistence and append-only review operations for the G06 graph."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def upsert_capability(self, name: str, *, status: str = "ACTIVE") -> Capability:
        normalized = _normalize(name)
        if not normalized:
            raise NormalizationError("capability name is required")
        if status not in {"ACTIVE", "RETIRED"}:
            raise NormalizationError(f"invalid capability status: {status}")
        capability_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO capabilities (capability_id, name, normalized_name, status) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (normalized_name) DO UPDATE SET status = EXCLUDED.status",
                (capability_id, name.strip(), normalized, status),
            )
            row = conn.execute(
                "SELECT capability_id, name, status FROM capabilities WHERE normalized_name = %s", (normalized,)
            ).fetchone()
        return Capability(_text(row[0]), _text(row[1]), _text(row[2]))

    def upsert_technology(self, name: str, *, kind: str = "UNKNOWN", status: str = "ACTIVE") -> Technology:
        normalized = _normalize(name)
        if not normalized or not kind.strip():
            raise NormalizationError("technology name and kind are required")
        if status not in {"ACTIVE", "RETIRED"}:
            raise NormalizationError(f"invalid technology status: {status}")
        technology_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO technologies (technology_id, name, normalized_name, kind, status) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (normalized_name) DO UPDATE SET kind = EXCLUDED.kind, status = EXCLUDED.status",
                (technology_id, name.strip(), normalized, kind.strip(), status),
            )
            row = conn.execute(
                "SELECT technology_id, name, kind, status FROM technologies WHERE normalized_name = %s", (normalized,)
            ).fetchone()
        return Technology(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]))

    def add_alias(self, capability_id: str, alias_text: str) -> str:
        normalized = _normalize(alias_text)
        if not normalized:
            raise NormalizationError("alias text is required")
        alias_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO capability_aliases (alias_id, capability_id, alias_text, normalized_alias) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (normalized_alias) DO UPDATE SET capability_id = EXCLUDED.capability_id, alias_text = EXCLUDED.alias_text",
                (alias_id, capability_id, alias_text.strip(), normalized),
            )
            row = conn.execute("SELECT alias_id FROM capability_aliases WHERE normalized_alias = %s", (normalized,)).fetchone()
        return _text(row[0])

    def mapping(
        self,
        *,
        receipt_id: str,
        candidate_text: str,
        entity_type: str,
        entity_id: str | None,
        normalizer_version: str,
        confidence: float,
        status: str,
        rationale: str,
    ) -> CandidateMapping:
        if entity_type not in {"CAPABILITY", "TECHNOLOGY"}:
            raise NormalizationError("entity_type must be CAPABILITY or TECHNOLOGY")
        if status not in _MAPPING_STATUSES or not 0 <= confidence <= 1:
            raise NormalizationError("invalid mapping status or confidence")
        if not candidate_text.strip() or not rationale.strip() or not normalizer_version.strip():
            raise NormalizationError("candidate_text, rationale, and normalizer_version are required")
        mapping_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO capability_mappings (mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (mapping_id, receipt_id, candidate_text.strip(), entity_type, entity_id, normalizer_version, confidence, status, rationale.strip()),
            )
            row = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale "
                "FROM capability_mappings WHERE receipt_id = %s AND entity_type = %s AND lower(candidate_text) = lower(%s) "
                "AND normalizer_version = %s AND COALESCE(entity_id, '') = COALESCE(%s, '') ORDER BY created_at LIMIT 1",
                (receipt_id, entity_type, candidate_text.strip(), normalizer_version, entity_id),
            ).fetchone()
        return _mapping(row)

    def relationship(self, capability_id: str, technology_id: str, *, relationship_type: str, confidence: float, mapping_id: str | None = None) -> CapabilityRelationship:
        if relationship_type not in {"IMPLEMENTS", "USED_WITH"} or not 0 <= confidence <= 1:
            raise NormalizationError("invalid relationship type or confidence")
        relationship_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO capability_relationships (relationship_id, capability_id, technology_id, relationship_type, confidence, status, mapping_id) "
                "VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s) ON CONFLICT (capability_id, technology_id, relationship_type) DO NOTHING",
                (relationship_id, capability_id, technology_id, relationship_type, confidence, mapping_id),
            )
            row = conn.execute(
                "SELECT relationship_id, capability_id, technology_id, relationship_type, confidence, status, mapping_id "
                "FROM capability_relationships WHERE capability_id = %s AND technology_id = %s AND relationship_type = %s",
                (capability_id, technology_id, relationship_type),
            ).fetchone()
        return _relationship(row)

    def list_mappings(self, *, receipt_id: str | None = None, entity_id: str | None = None, limit: int = 500) -> list[CandidateMapping]:
        if not 1 <= limit <= 500:
            raise EvidenceValidationError("limit must be between 1 and 500")
        clauses, params = [], []
        if receipt_id:
            clauses.append("receipt_id = %s")
            params.append(receipt_id)
        if entity_id:
            clauses.append("entity_id = %s")
            params.append(entity_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale "
                f"FROM capability_mappings {where} ORDER BY created_at, mapping_id LIMIT %s", params
            ).fetchall()
        return [_mapping(row) for row in rows]

    def list_relationships(self, *, capability_id: str | None = None, technology_id: str | None = None) -> list[CapabilityRelationship]:
        clauses, params = [], []
        if capability_id:
            clauses.append("capability_id = %s")
            params.append(capability_id)
        if technology_id:
            clauses.append("technology_id = %s")
            params.append(technology_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT relationship_id, capability_id, technology_id, relationship_type, confidence, status, mapping_id "
                f"FROM capability_relationships {where} ORDER BY created_at", params
            ).fetchall()
        return [_relationship(row) for row in rows]

    def inspect_capability(self, capability_id: str) -> CapabilityInspection | None:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT capability_id, name, status FROM capabilities WHERE capability_id = %s", (capability_id,)).fetchone()
            if row is None:
                return None
            concepts = conn.execute("SELECT name FROM capability_concepts WHERE capability_id = %s ORDER BY name", (capability_id,)).fetchall()
            patterns = conn.execute("SELECT name FROM capability_patterns WHERE capability_id = %s ORDER BY name", (capability_id,)).fetchall()
            technologies = conn.execute(
                "SELECT t.technology_id, t.name, t.kind, t.status FROM technologies t JOIN capability_relationships r ON r.technology_id = t.technology_id "
                "WHERE r.capability_id = %s AND r.status = 'ACTIVE' ORDER BY t.name", (capability_id,)
            ).fetchall()
            mappings = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale "
                "FROM capability_mappings WHERE entity_id = %s ORDER BY created_at", (capability_id,)
            ).fetchall()
            decisions = conn.execute(
                "SELECT d.decision_id, d.mapping_id, d.action, d.actor, d.reason, d.previous_entity_id, d.previous_status, d.new_entity_id, d.new_status "
                "FROM normalization_decisions d JOIN capability_mappings m ON m.mapping_id = d.mapping_id WHERE m.entity_id = %s ORDER BY d.created_at", (capability_id,)
            ).fetchall()
        return CapabilityInspection(
            capability=Capability(_text(row[0]), _text(row[1]), _text(row[2])),
            concepts=[_text(item[0]) for item in concepts], patterns=[_text(item[0]) for item in patterns],
            technologies=[Technology(_text(item[0]), _text(item[1]), _text(item[2]), _text(item[3])) for item in technologies],
            mappings=[_mapping(item) for item in mappings], decisions=[_decision(item) for item in decisions],
        )

    def review(self, mapping_id: str, action: str, *, actor: str, reason: str, entity_id: str | None = None) -> CandidateMapping:
        if action not in _ACTIONS or not actor.strip() or not reason.strip():
            raise NormalizationError("invalid review action, actor, or reason")
        if action in {"REMAP"} and not entity_id:
            raise NormalizationError("REMAP requires entity_id")
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale FROM capability_mappings WHERE mapping_id = %s FOR UPDATE",
                (mapping_id,),
            ).fetchone()
            if row is None:
                raise NormalizationError("mapping not found")
            current = _mapping(row)
            if action == "UNDO":
                prior = conn.execute(
                    "SELECT previous_entity_id, previous_status FROM normalization_decisions WHERE mapping_id = %s AND action <> 'UNDO' ORDER BY created_at DESC LIMIT 1",
                    (mapping_id,),
                ).fetchone()
                if prior is None or prior[1] is None:
                    raise NormalizationError("mapping has no reversible decision")
                new_entity, new_status = prior[0], _text(prior[1])
            else:
                new_entity = entity_id if action == "REMAP" else current.entity_id
                new_status = {"ACCEPT": "ACCEPTED", "REJECT": "REJECTED", "REMAP": "ACCEPTED", "SPLIT": "SUPERSEDED"}[action]
            decision_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO normalization_decisions (decision_id, mapping_id, action, actor, reason, previous_entity_id, previous_status, new_entity_id, new_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (decision_id, mapping_id, action, actor.strip(), reason.strip(), current.entity_id, current.status, new_entity, new_status),
            )
            conn.execute("UPDATE capability_mappings SET entity_id = %s, status = %s, updated_at = now() WHERE mapping_id = %s", (new_entity, new_status, mapping_id))
            updated = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale FROM capability_mappings WHERE mapping_id = %s", (mapping_id,)
            ).fetchone()
        return _mapping(updated)

    def split(self, mapping_id: str, names: list[str], *, actor: str, reason: str) -> list[CandidateMapping]:
        if len(names) < 2 or any(not name.strip() for name in names):
            raise NormalizationError("SPLIT requires at least two non-empty names")
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale FROM capability_mappings WHERE mapping_id = %s FOR UPDATE", (mapping_id,)
            ).fetchone()
            if row is None:
                raise NormalizationError("mapping not found")
            current = _mapping(row)
            if current.entity_type != "CAPABILITY":
                raise NormalizationError("only capability mappings can be split")
            conn.execute(
                "INSERT INTO normalization_decisions (decision_id, mapping_id, action, actor, reason, previous_entity_id, previous_status, new_entity_id, new_status) VALUES (%s, %s, 'SPLIT', %s, %s, %s, %s, NULL, 'SUPERSEDED')",
                (str(uuid.uuid4()), mapping_id, actor.strip(), reason.strip(), current.entity_id, current.status),
            )
            conn.execute("UPDATE capability_mappings SET status = 'SUPERSEDED', updated_at = now() WHERE mapping_id = %s", (mapping_id,))
            created = []
            for name in names:
                cap_id = str(uuid.uuid4())
                normalized = _normalize(name)
                conn.execute("INSERT INTO capabilities (capability_id, name, normalized_name, status) VALUES (%s, %s, %s, 'ACTIVE') ON CONFLICT (normalized_name) DO NOTHING", (cap_id, name.strip(), normalized))
                actual = conn.execute("SELECT capability_id FROM capabilities WHERE normalized_name = %s", (normalized,)).fetchone()[0]
                new_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO capability_mappings (mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale) VALUES (%s, %s, %s, 'CAPABILITY', %s, %s, %s, 'ACCEPTED', %s)",
                    (new_id, current.receipt_id, current.candidate_text, actual, current.normalizer_version, current.confidence, f"Split from {mapping_id}: {reason.strip()}"),
                )
                new_row = conn.execute("SELECT mapping_id, receipt_id, candidate_text, entity_type, entity_id, normalizer_version, confidence, status, rationale FROM capability_mappings WHERE mapping_id = %s", (new_id,)).fetchone()
                created.append(_mapping(new_row))
        return created


class DeterministicNormalizer:
    """Constrained alias normalizer used for offline evaluation and dogfood."""

    version = "aliases-v1"
    CAPABILITY_ALIASES = {
        "checkpoint recovery": "durable execution",
        "resumable agents": "durable execution",
        "workflow replay": "durable execution",
        "durable execution": "durable execution",
        "agent memory": "agent memory",
        "workflow persistence": "workflow persistence",
        "build evaluation systems": "evaluation",
        "evaluation systems": "evaluation",
        "evaluation": "evaluation",
    }

    def normalize(self, receipt: EvidenceReceipt) -> Mapping[str, Any]:
        capabilities = []
        for candidate in receipt.capability_candidates:
            key = _normalize(candidate)
            name = self.CAPABILITY_ALIASES.get(key, key)
            confidence = 0.95 if key in self.CAPABILITY_ALIASES else 0.60
            status = "ACCEPTED" if confidence >= 0.9 else "PROPOSED"
            capabilities.append({"candidate_text": candidate, "name": name, "confidence": confidence, "status": status, "rationale": "deterministic alias" if key in self.CAPABILITY_ALIASES else "unmatched candidate"})
        technologies = []
        for candidate in receipt.technology_candidates:
            technologies.append({"candidate_text": candidate, "name": candidate.strip(), "kind": _technology_kind(candidate), "confidence": 0.90, "status": "ACCEPTED", "rationale": "receipt technology candidate"})
        relationships = []
        for capability in capabilities:
            for technology in technologies:
                relationships.append({"capability_name": capability["name"], "technology_name": technology["name"], "relationship_type": "IMPLEMENTS", "confidence": min(capability["confidence"], technology["confidence"])})
        return {"capabilities": capabilities, "technologies": technologies, "relationships": relationships}


class NormalizationService:
    def __init__(self, receipts: ReceiptRepository, repository: CapabilityRepository, normalizer: Normalizer):
        self.receipts, self.repository, self.normalizer = receipts, repository, normalizer

    def normalize(self, receipt_ids: Iterable[str] | None = None, *, limit: int = 100, force: bool = False) -> NormalizationSummary:
        if not 1 <= limit <= 500:
            raise EvidenceValidationError("limit must be between 1 and 500")
        receipts = [self.receipts.get_receipt(item) for item in receipt_ids] if receipt_ids else self.receipts.list_receipts(limit=limit)
        receipts = [item for item in receipts if item is not None][:limit]
        processed = cached = 0
        mappings: list[CandidateMapping] = []
        relationships: list[CapabilityRelationship] = []
        for receipt in receipts:
            existing = self.repository.list_mappings(receipt_id=receipt.receipt_id, limit=500)
            if existing and not force and all(item.normalizer_version == self.normalizer.version for item in existing):
                cached += 1
                mappings.extend(existing)
                continue
            output = self.normalizer.normalize(receipt)
            caps: dict[str, Capability] = {}
            techs: dict[str, Technology] = {}
            for item in output.get("capabilities", []):
                cap = self.repository.upsert_capability(item["name"], status="ACTIVE")
                caps[_normalize(item["name"])] = cap
                mappings.append(self.repository.mapping(receipt_id=receipt.receipt_id, candidate_text=item["candidate_text"], entity_type="CAPABILITY", entity_id=cap.capability_id, normalizer_version=self.normalizer.version, confidence=float(item["confidence"]), status=item["status"], rationale=item["rationale"]))
            for item in output.get("technologies", []):
                tech = self.repository.upsert_technology(item["name"], kind=item.get("kind", "UNKNOWN"), status="ACTIVE")
                techs[_normalize(item["name"])] = tech
                mappings.append(self.repository.mapping(receipt_id=receipt.receipt_id, candidate_text=item["candidate_text"], entity_type="TECHNOLOGY", entity_id=tech.technology_id, normalizer_version=self.normalizer.version, confidence=float(item["confidence"]), status=item["status"], rationale=item["rationale"]))
            for item in output.get("relationships", []):
                cap = caps.get(_normalize(item["capability_name"]))
                tech = techs.get(_normalize(item["technology_name"]))
                if cap and tech:
                    relationships.append(self.repository.relationship(cap.capability_id, tech.technology_id, relationship_type=item["relationship_type"], confidence=float(item["confidence"])))
            processed += 1
        return NormalizationSummary(processed, cached, mappings, relationships)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _technology_kind(value: str) -> str:
    lowered = _normalize(value)
    if any(token in lowered for token in ("framework", "langgraph", "temporal", "dagster", "airflow")):
        return "FRAMEWORK"
    if lowered in {"python", "postgres", "postgresql", "redis"}:
        return "LANGUAGE_OR_DATABASE"
    return "TOOL"


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value


def _mapping(row: tuple[Any, ...]) -> CandidateMapping:
    return CandidateMapping(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), _text(row[5]), float(row[6]), _text(row[7]), _text(row[8]))


def _relationship(row: tuple[Any, ...]) -> CapabilityRelationship:
    return CapabilityRelationship(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), float(row[4]), _text(row[5]), _text(row[6]))


def _decision(row: tuple[Any, ...]) -> ReviewDecision:
    return ReviewDecision(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), _text(row[5]), _text(row[6]), _text(row[7]), _text(row[8]))
