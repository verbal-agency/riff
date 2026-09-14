"""Explicit Riff lifecycle decisions, semantic feedback, and resurfacing."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection


DECISIONS = {"WATCH", "REJECT", "ARCHIVE", "APPROVE_EXPLORATION", "CONFIRM_PROFILE_UPDATE", "CORRECT"}
ACTOR_KINDS = {"USER", "MODEL", "SYSTEM"}
LEGAL_TRANSITIONS = {
    "PUBLISHED": {"WATCHING": "WATCH", "REJECTED": "REJECT", "ARCHIVED": "ARCHIVE", "EXPLORING": "APPROVE_EXPLORATION"},
    "NEW": {"WATCHING": "WATCH", "REJECTED": "REJECT", "ARCHIVED": "ARCHIVE", "EXPLORING": "APPROVE_EXPLORATION"},
    "WATCHING": {"WATCHING": "WATCH", "REJECTED": "REJECT", "ARCHIVED": "ARCHIVE", "EXPLORING": "APPROVE_EXPLORATION"},
    "REJECTED": {"ARCHIVED": "ARCHIVE"},
    "EXPLORING": {"ARCHIVED": "ARCHIVE"},
    "ARCHIVED": {},
}


class DecisionError(ValueError):
    """An invalid decision, transition, actor boundary, or resurfacing request."""


@dataclass(frozen=True, slots=True)
class Decision:
    decision_id: str
    riff_id: str
    decision: str
    actor: str
    actor_kind: str
    reason: str
    structured_reason: dict[str, Any]
    semantic_implications: dict[str, Any]
    evidence_snapshot: tuple[str, ...]
    policy_version: str
    supersedes_decision_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Investigation:
    riff_id: str
    status: str
    riff: dict[str, Any]
    supporting_evidence: tuple[dict[str, Any], ...]
    counterevidence: tuple[dict[str, Any], ...]
    profile_slice: tuple[dict[str, Any], ...]
    decision_history: tuple[Decision, ...]
    source_breakdown: dict[str, int]


@dataclass(frozen=True, slots=True)
class ResurfaceEvent:
    resurface_id: str
    riff_id: str
    previous_decision_id: str
    new_receipt_ids: tuple[str, ...]
    explanation: str
    policy_version: str


def infer_implications(reason: str) -> dict[str, Any]:
    text = reason.lower()
    implications: dict[str, Any] = {"novelty_adjustment": 0.0, "relevance_adjustment": 0.0, "framework_adoption_penalty": 0.0, "underlying_capability_interest": 0.0, "profile_update_proposed": False, "signals": []}
    if any(term in text for term in ("framework-specific", "framework specific", "vendor churn", "vendor-specific", "too framework")):
        implications.update(framework_adoption_penalty=-1.0, underlying_capability_interest=1.0)
        implications["signals"].extend(["FRAMEWORK_ADOPTION_AVERSION", "UNDERLYING_CAPABILITY_INTEREST"])
    if any(term in text for term in ("already understand", "understand this professionally", "already know")):
        implications["profile_update_proposed"] = True
        implications["novelty_adjustment"] = -0.5
        implications["signals"].append("PROFESSIONAL_KNOWLEDGE_CLAIM")
    if any(term in text for term in ("not novel", "already established", "nothing new")):
        implications["novelty_adjustment"] = -1.0
        implications["signals"].append("NOVELTY_AVERSION")
    if any(term in text for term in ("not relevant", "doesn't matter", "irrelevant")):
        implications["relevance_adjustment"] = -1.0
        implications["signals"].append("RELEVANCE_AVERSION")
    return implications


class DecisionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _riff_status(self, conn, riff_id: str) -> str:
        row = conn.execute("SELECT status FROM riffs WHERE riff_id = %s FOR UPDATE", (riff_id,)).fetchone()
        if row is None:
            raise DecisionError("Riff not found")
        return _text(row[0])

    def record_decision(self, riff_id: str, decision: str, reason: str, *, actor: str = "user", actor_kind: str = "USER", structured_reason: Mapping[str, Any] | None = None, policy_version: str = "decision-policy-v1", supersedes_decision_id: str | None = None) -> Decision:
        if decision not in DECISIONS:
            raise DecisionError(f"unsupported decision: {decision}")
        if actor_kind not in ACTOR_KINDS or not actor.strip() or not reason.strip():
            raise DecisionError("actor, actor_kind, and reason are required")
        if decision in {"WATCH", "REJECT", "ARCHIVE", "APPROVE_EXPLORATION"} and actor_kind != "USER":
            raise DecisionError("lifecycle transitions require an explicit user-originated decision")
        with connection(self.database_url) as conn:
            current = self._riff_status(conn, riff_id)
            target = None
            for candidate, action in LEGAL_TRANSITIONS.get(current, {}).items():
                if action == decision:
                    target = candidate
                    break
            if decision == "APPROVE_EXPLORATION" and current not in {"PUBLISHED", "NEW", "WATCHING"}:
                raise DecisionError(f"cannot approve exploration from {current}")
            if decision in {"WATCH", "REJECT", "ARCHIVE", "APPROVE_EXPLORATION"} and target is None:
                raise DecisionError(f"illegal transition {current} -> {decision}")
            support_row = conn.execute("SELECT supporting_receipt_ids, counter_receipt_ids FROM riffs WHERE riff_id = %s", (riff_id,)).fetchone()
            snapshot = tuple(_json(support_row[0]) + _json(support_row[1])) if support_row else ()
            decision_id = str(uuid.uuid4())
            implications = infer_implications(reason)
            row = conn.execute("""INSERT INTO riff_decisions
                (decision_id, riff_id, decision, actor, actor_kind, reason, structured_reason,
                 semantic_implications, evidence_snapshot, policy_version, supersedes_decision_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING decision_id, riff_id, decision, actor, actor_kind, reason,
                          structured_reason, semantic_implications, evidence_snapshot,
                          policy_version, supersedes_decision_id, created_at""",
                (decision_id, riff_id, decision, actor.strip(), actor_kind, reason, Jsonb(dict(structured_reason or {})), Jsonb(implications), Jsonb(list(snapshot)), policy_version, supersedes_decision_id),
            ).fetchone()
            if target:
                conn.execute("UPDATE riffs SET status = %s WHERE riff_id = %s", (target, riff_id))
                conn.execute("INSERT INTO riff_status_history (transition_id, riff_id, from_status, to_status, decision_id, actor, actor_kind) VALUES (%s, %s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), riff_id, current, target, decision_id, actor.strip(), actor_kind))
        return _decision(row)

    def list_decisions(self, riff_id: str, *, limit: int = 100) -> list[Decision]:
        if not 1 <= limit <= 500:
            raise DecisionError("limit must be between 1 and 500")
        with connection(self.database_url) as conn:
            rows = conn.execute("""SELECT decision_id, riff_id, decision, actor, actor_kind, reason,
                structured_reason, semantic_implications, evidence_snapshot, policy_version,
                supersedes_decision_id, created_at FROM riff_decisions
                WHERE riff_id = %s ORDER BY created_at LIMIT %s""", (riff_id, limit)).fetchall()
        return [_decision(row) for row in rows]

    def investigation(self, riff_id: str) -> Investigation:
        with connection(self.database_url) as conn:
            riff = conn.execute("""SELECT riff_id, daily_run_id, candidate_id, status, observation, hypothesis, why_now,
                why_it_matters, user_relevance, underlying_capability, recommendation,
                confidence, strongest_counterargument, alternative_explanation,
                falsification_conditions, associated_technologies, supporting_receipt_ids,
                counter_receipt_ids FROM riffs WHERE riff_id = %s""", (riff_id,)).fetchone()
            if riff is None:
                raise DecisionError("Riff not found")
            riff_data = {"riff_id": _text(riff[0]), "status": _text(riff[3]), "observation": _text(riff[4]), "hypothesis": _text(riff[5]), "why_now": _text(riff[6]), "why_it_matters": _text(riff[7]), "user_relevance": _text(riff[8]), "underlying_capability": _text(riff[9]), "recommendation": _text(riff[10]), "confidence": float(riff[11]), "strongest_counterargument": _text(riff[12]), "alternative_explanation": _text(riff[13]), "falsification_conditions": _json(riff[14]), "associated_technologies": _json(riff[15])}
            support_ids, counter_ids = _json(riff[16]), _json(riff[17])
            evidence = conn.execute("""SELECT e.evidence_id, e.raw_content, si.canonical_url, si.title,
                r.receipt_id, r.summary, r.source_metadata FROM evidence_versions e
                JOIN source_items si ON si.source_item_id = e.source_item_id
                JOIN evidence_receipts r ON r.evidence_id = e.evidence_id
                WHERE r.receipt_id = ANY(%s) ORDER BY r.receipt_id""", (support_ids + counter_ids,)).fetchall() if support_ids + counter_ids else []
            contexts = conn.execute("SELECT profile_slice FROM riff_contexts WHERE daily_run_id = %s AND candidate_id = %s ORDER BY created_at DESC LIMIT 1", (riff[1], riff[2])).fetchone() if riff[2] else None
        support_set, source_breakdown = set(support_ids), {}
        supporting, counter = [], []
        for row in evidence:
            item = {"receipt_id": _text(row[4]), "evidence_id": _text(row[0]), "summary": _text(row[5]), "raw_content": _text(row[1]), "canonical_url": _text(row[2]), "title": _text(row[3]), "source_metadata": _json(row[6])}
            source = str(item["source_metadata"].get("source_type", "UNKNOWN"))
            source_breakdown[source] = source_breakdown.get(source, 0) + 1
            (supporting if item["receipt_id"] in support_set else counter).append(item)
        return Investigation(_text(riff[0]), _text(riff[3]), riff_data, tuple(supporting), tuple(counter), tuple(_json(contexts[0])) if contexts else (), tuple(self.list_decisions(riff_id)), source_breakdown)

    def effective_implications(self, riff_id: str) -> dict[str, Any]:
        decisions = self.list_decisions(riff_id)
        result: dict[str, Any] = {"novelty_adjustment": 0.0, "relevance_adjustment": 0.0, "framework_adoption_penalty": 0.0, "underlying_capability_interest": 0.0, "profile_update_proposed": False, "profile_update_confirmed": False}
        for item in decisions:
            if item.decision == "CONFIRM_PROFILE_UPDATE":
                result["profile_update_confirmed"] = True
            for key in ("novelty_adjustment", "relevance_adjustment", "framework_adoption_penalty", "underlying_capability_interest"):
                if key in item.semantic_implications:
                    result[key] += float(item.semantic_implications[key])
            if item.semantic_implications.get("profile_update_proposed"):
                result["profile_update_proposed"] = True
        if result["profile_update_proposed"] and not result["profile_update_confirmed"]:
            result["novelty_adjustment"] = 0.0
        return result

    def resurface_if_changed(self, riff_id: str, current_receipt_ids: Sequence[str], *, policy_version: str = "resurface-policy-v1") -> ResurfaceEvent | None:
        current = set(current_receipt_ids)
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT status FROM riffs WHERE riff_id = %s FOR UPDATE", (riff_id,)).fetchone()
            if row is None:
                raise DecisionError("Riff not found")
            if _text(row[0]) != "REJECTED":
                return None
            prior = conn.execute("SELECT decision_id, evidence_snapshot, reason FROM riff_decisions WHERE riff_id = %s AND decision = 'REJECT' ORDER BY created_at DESC LIMIT 1", (riff_id,)).fetchone()
            if prior is None:
                raise DecisionError("rejected Riff has no rejection decision")
            snapshot = set(_json(prior[1]))
            new_ids = sorted(current - snapshot)
            if not new_ids:
                return None
            decision_id = str(uuid.uuid4())
            reason = f"Material evidence change: {len(new_ids)} new receipt(s) since rejection."
            conn.execute("INSERT INTO riff_decisions (decision_id, riff_id, decision, actor, actor_kind, reason, structured_reason, semantic_implications, evidence_snapshot, policy_version) VALUES (%s, %s, 'WATCH', 'resurfacer', 'SYSTEM', %s, %s, %s, %s, %s)", (decision_id, riff_id, reason, Jsonb({"resurfaced": True}), Jsonb({"material_change": True}), Jsonb(new_ids), policy_version))
            conn.execute("UPDATE riffs SET status = 'WATCHING' WHERE riff_id = %s", (riff_id,))
            conn.execute("INSERT INTO riff_status_history (transition_id, riff_id, from_status, to_status, decision_id, actor, actor_kind) VALUES (%s, %s, 'REJECTED', 'WATCHING', %s, 'resurfacer', 'SYSTEM')", (str(uuid.uuid4()), riff_id, decision_id))
            event_id = str(uuid.uuid4())
            explanation = f"Previously rejected because: {prior[2]}. New independent receipt IDs: {', '.join(new_ids)}."
            conn.execute("INSERT INTO riff_resurface_events (resurface_id, riff_id, previous_decision_id, new_receipt_ids, explanation, policy_version) VALUES (%s, %s, %s, %s, %s, %s)", (event_id, riff_id, prior[0], Jsonb(new_ids), explanation, policy_version))
        return ResurfaceEvent(event_id, riff_id, _text(prior[0]), tuple(new_ids), explanation, policy_version)


def _decision(row: tuple[Any, ...]) -> Decision:
    return Decision(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), _text(row[5]), _json(row[6]), _json(row[7]), tuple(_json(row[8])), _text(row[9]), _text(row[10]) if row[10] else None, row[11])


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, str)):
        return json.loads(value.decode() if isinstance(value, bytes) else value)
    return value or []


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode()
    return value
