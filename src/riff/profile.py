"""Privacy-aware user capability profile and gap assessment."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceValidationError


EVIDENCE_LEVELS = {
    "PUBLICLY_DEMONSTRATED", "PROFESSIONALLY_DEMONSTRATED_PRIVATE", "HANDS_ON_PERSONAL",
    "STUDIED", "CONCEPTUALLY_FAMILIAR", "UNKNOWN",
}
GAP_CLASSIFICATIONS = {"KNOWLEDGE_GAP", "IMPLEMENTATION_GAP", "SIGNALING_GAP", "EXPERIENCE_GAP", "NO_MEANINGFUL_GAP", "UNKNOWN"}


class ProfileValidationError(ValueError):
    """Profile evidence or privacy boundary is invalid."""


@dataclass(frozen=True, slots=True)
class ProfileEvidence:
    profile_evidence_id: str
    capability_id: str
    evidence_level: str
    visibility: str
    origin: str
    confidence: float
    description: str
    reference: str | None
    observed_at: datetime | None
    status: str
    source_evidence_id: str | None
    attestation_state: str


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    ledger_id: str
    profile_evidence_id: str
    entry_text: str
    employer_or_context: str | None
    attestation_state: str


@dataclass(frozen=True, slots=True)
class GapAssessment:
    assessment_id: str
    capability_id: str
    classification: str
    rationale: str
    uncertainty: dict[str, Any]
    evidence_snapshot: list[dict[str, Any]]
    computed_at: datetime


@dataclass(frozen=True, slots=True)
class ProfileView:
    capability_id: str
    evidence: list[ProfileEvidence]
    assessment: GapAssessment | None


class ProfileRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def create_evidence(
        self,
        capability_id: str,
        *,
        evidence_level: str,
        visibility: str,
        origin: str,
        confidence: float,
        description: str,
        reference: str | None = None,
        observed_at: datetime | None = None,
        source_evidence_id: str | None = None,
        attestation_state: str = "UNVERIFIED",
        actor: str = "user",
    ) -> ProfileEvidence:
        _validate_evidence(evidence_level, visibility, origin, confidence, description, attestation_state)
        evidence_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO profile_evidence (profile_evidence_id, capability_id, evidence_level, visibility, origin, confidence, description, reference, observed_at, status, source_evidence_id, attestation_state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s)",
                (evidence_id, capability_id, evidence_level, visibility, origin, confidence, description.strip(), reference, observed_at, source_evidence_id, attestation_state),
            )
            item = self._get_row(conn, evidence_id)
            self._history(conn, evidence_id, "CREATE", actor, "profile evidence created", None, item)
        return _evidence(item)

    def create_ledger_entry(self, capability_id: str, entry_text: str, *, employer_or_context: str | None = None, actor: str = "user") -> LedgerEntry:
        evidence = self.create_evidence(
            capability_id,
            evidence_level="PROFESSIONALLY_DEMONSTRATED_PRIVATE",
            visibility="PRIVATE",
            origin="EXPERIENCE_LEDGER",
            confidence=1.0,
            description=entry_text,
            attestation_state="USER_ATTESTED",
            actor=actor,
        )
        ledger_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO experience_ledger (ledger_id, profile_evidence_id, entry_text, employer_or_context, attestation_state) VALUES (%s, %s, %s, %s, 'USER_ATTESTED')",
                (ledger_id, evidence.profile_evidence_id, entry_text.strip(), employer_or_context),
            )
        return LedgerEntry(ledger_id, evidence.profile_evidence_id, entry_text.strip(), employer_or_context, "USER_ATTESTED")

    def list_ledger_entries(self, *, limit: int = 100) -> list[LedgerEntry]:
        if not 1 <= limit <= 500:
            raise ProfileValidationError("limit must be between 1 and 500")
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT ledger_id, profile_evidence_id, entry_text, employer_or_context, attestation_state FROM experience_ledger ORDER BY created_at LIMIT %s", (limit,)
            ).fetchall()
        return [LedgerEntry(*(_text(value) for value in row)) for row in rows]

    def update_ledger_entry(self, ledger_id: str, entry_text: str, *, employer_or_context: str | None = None, actor: str = "user", reason: str = "ledger correction") -> LedgerEntry:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT profile_evidence_id, employer_or_context FROM experience_ledger WHERE ledger_id = %s", (ledger_id,)).fetchone()
        if row is None:
            raise ProfileValidationError("ledger entry not found")
        evidence = self.update_evidence(_text(row[0]), description=entry_text, actor=actor, reason=reason)
        context = employer_or_context if employer_or_context is not None else _text(row[1])
        with connection(self.database_url) as conn:
            conn.execute("UPDATE experience_ledger SET entry_text = %s, employer_or_context = %s WHERE ledger_id = %s", (entry_text.strip(), context, ledger_id))
            item = conn.execute("SELECT ledger_id, profile_evidence_id, entry_text, employer_or_context, attestation_state FROM experience_ledger WHERE ledger_id = %s", (ledger_id,)).fetchone()
        return LedgerEntry(*(_text(value) for value in item))

    def archive_ledger_entry(self, ledger_id: str, *, actor: str = "user", reason: str = "ledger archived") -> ProfileEvidence:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT profile_evidence_id FROM experience_ledger WHERE ledger_id = %s", (ledger_id,)).fetchone()
        if row is None:
            raise ProfileValidationError("ledger entry not found")
        return self.archive_evidence(_text(row[0]), actor=actor, reason=reason)

    def get_evidence(self, profile_evidence_id: str) -> ProfileEvidence | None:
        with connection(self.database_url) as conn:
            row = self._get_row(conn, profile_evidence_id)
        return _evidence(row) if row else None

    def update_evidence(self, profile_evidence_id: str, *, actor: str = "user", reason: str = "correction", **changes: Any) -> ProfileEvidence:
        allowed = {"evidence_level", "visibility", "origin", "confidence", "description", "reference", "observed_at", "source_evidence_id", "attestation_state"}
        if not changes or set(changes) - allowed:
            raise ProfileValidationError("provide only supported evidence corrections")
        current = self.get_evidence(profile_evidence_id)
        if current is None:
            raise ProfileValidationError("profile evidence not found")
        values = {field: getattr(current, field) for field in allowed}
        values.update(changes)
        _validate_evidence(values["evidence_level"], values["visibility"], values["origin"], values["confidence"], values["description"], values["attestation_state"])
        with connection(self.database_url) as conn:
            before = self._get_row(conn, profile_evidence_id)
            assignments = ", ".join(f"{field} = %s" for field in changes) + ", updated_at = now()"
            conn.execute(f"UPDATE profile_evidence SET {assignments} WHERE profile_evidence_id = %s", [changes[field] for field in changes] + [profile_evidence_id])
            after = self._get_row(conn, profile_evidence_id)
            self._history(conn, profile_evidence_id, "CORRECT", actor, reason, before, after)
        return _evidence(after)

    def archive_evidence(self, profile_evidence_id: str, *, actor: str = "user", reason: str = "archived") -> ProfileEvidence:
        with connection(self.database_url) as conn:
            before = self._get_row(conn, profile_evidence_id)
            if before is None:
                raise ProfileValidationError("profile evidence not found")
            conn.execute("UPDATE profile_evidence SET status = 'ARCHIVED', updated_at = now() WHERE profile_evidence_id = %s", (profile_evidence_id,))
            after = self._get_row(conn, profile_evidence_id)
            self._history(conn, profile_evidence_id, "ARCHIVE", actor, reason, before, after)
        return _evidence(after)

    def list_evidence(self, capability_id: str, *, view: str = "PERSONAL", limit: int = 100) -> list[ProfileEvidence]:
        if view not in {"PERSONAL", "PUBLIC"} or not 1 <= limit <= 500:
            raise ProfileValidationError("view must be PERSONAL or PUBLIC and limit 1..500")
        visibility = " AND visibility = 'PUBLIC'" if view == "PUBLIC" else ""
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT profile_evidence_id, capability_id, evidence_level, visibility, origin, confidence, description, reference, observed_at, status, source_evidence_id, attestation_state FROM profile_evidence "
                f"WHERE capability_id = %s AND status = 'ACTIVE'{visibility} ORDER BY observed_at NULLS LAST, created_at LIMIT %s", (capability_id, limit)
            ).fetchall()
        return [_evidence(row) for row in rows]

    def assess(self, capability_id: str) -> GapAssessment:
        evidence = self.list_evidence(capability_id, view="PERSONAL")
        levels = {item.evidence_level for item in evidence}
        public = [item for item in evidence if item.visibility == "PUBLIC"]
        private_professional = any(item.evidence_level == "PROFESSIONALLY_DEMONSTRATED_PRIVATE" for item in evidence)
        public_demo = any(item.evidence_level == "PUBLICLY_DEMONSTRATED" for item in public)
        hands_on = any(item.evidence_level == "HANDS_ON_PERSONAL" for item in evidence)
        conflicting_weak = any(item.origin == "GITHUB" for item in evidence) and any(item.evidence_level in {"STUDIED", "CONCEPTUALLY_FAMILIAR"} for item in evidence)
        if private_professional and not public_demo and not hands_on:
            classification, rationale = "SIGNALING_GAP", "Private professional evidence exists without public demonstration."
        elif public_demo or hands_on:
            classification, rationale = "NO_MEANINGFUL_GAP", "Public or hands-on evidence demonstrates the capability."
        elif conflicting_weak:
            classification, rationale = "UNKNOWN", "Public mention and self-described familiarity conflict without implementation evidence."
        elif "STUDIED" in levels or "CONCEPTUALLY_FAMILIAR" in levels:
            classification, rationale = "IMPLEMENTATION_GAP", "Familiarity is present, but no hands-on or demonstrated evidence is recorded."
        elif any(item.origin == "GITHUB" for item in evidence):
            classification, rationale = "UNKNOWN", "A technology mention is insufficient to infer capability proficiency."
        else:
            classification, rationale = "UNKNOWN", "Evidence is sparse or insufficient to classify the gap."
        snapshot = [{"profile_evidence_id": item.profile_evidence_id, "level": item.evidence_level, "visibility": item.visibility, "origin": item.origin, "confidence": item.confidence} for item in evidence]
        uncertainty = {"evidence_count": len(evidence), "private_count": sum(item.visibility == "PRIVATE" for item in evidence), "public_count": len(public)}
        assessment_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            row = conn.execute(
                "INSERT INTO gap_assessments (assessment_id, capability_id, classification, rationale, uncertainty, evidence_snapshot) VALUES (%s, %s, %s, %s, %s, %s) RETURNING assessment_id, capability_id, classification, rationale, uncertainty, evidence_snapshot, computed_at",
                (assessment_id, capability_id, classification, rationale, Jsonb(uncertainty), Jsonb(snapshot)),
            ).fetchone()
        return _assessment(row)

    def view(self, capability_id: str, *, public: bool = False, limit: int = 100) -> ProfileView:
        evidence = self.list_evidence(capability_id, view="PUBLIC" if public else "PERSONAL", limit=limit)
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT assessment_id, capability_id, classification, rationale, uncertainty, evidence_snapshot, computed_at FROM gap_assessments WHERE capability_id = %s ORDER BY computed_at DESC LIMIT 1", (capability_id,)
            ).fetchone()
        return ProfileView(capability_id, evidence, _assessment(row) if row else None)

    def history(self, target_id: str) -> list[dict[str, Any]]:
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT event_id, target_id, action, actor, reason, before_state, after_state, created_at FROM profile_history WHERE target_id = %s ORDER BY created_at", (target_id,)).fetchall()
        return [{"event_id": _text(row[0]), "target_id": _text(row[1]), "action": _text(row[2]), "actor": _text(row[3]), "reason": _text(row[4]), "before": _json(row[5]), "after": _json(row[6]), "created_at": row[7]} for row in rows]

    def import_public_fixture(self, path: str, *, limit: int = 100) -> list[ProfileEvidence]:
        if not 1 <= limit <= 500:
            raise ProfileValidationError("limit must be between 1 and 500")
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProfileValidationError("public profile fixture could not be read") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("items"), list):
            raise ProfileValidationError("public profile fixture requires schema_version 1 and items")
        imported = []
        for item in payload["items"][:limit]:
            if not isinstance(item, Mapping):
                raise ProfileValidationError("public profile item must be an object")
            imported.append(self.create_evidence(
                item["capability_id"], evidence_level=item.get("evidence_level", "UNKNOWN"), visibility="PUBLIC",
                origin=item.get("origin", "WEBSITE"), confidence=float(item.get("confidence", 0.5)),
                description=item["description"], reference=item.get("reference"), attestation_state="UNVERIFIED", actor="importer",
            ))
        return imported

    @staticmethod
    def _get_row(conn, evidence_id: str):
        return conn.execute("SELECT profile_evidence_id, capability_id, evidence_level, visibility, origin, confidence, description, reference, observed_at, status, source_evidence_id, attestation_state FROM profile_evidence WHERE profile_evidence_id = %s", (evidence_id,)).fetchone()

    @staticmethod
    def _history(conn, target_id, action, actor, reason, before, after):
        conn.execute("INSERT INTO profile_history (event_id, target_id, action, actor, reason, before_state, after_state) VALUES (%s, %s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), target_id, action, actor, reason, Jsonb(_state(before)), Jsonb(_state(after))))


def _validate_evidence(level, visibility, origin, confidence, description, attestation):
    if level not in EVIDENCE_LEVELS or visibility not in {"PUBLIC", "PRIVATE"} or origin not in {"GITHUB", "WEBSITE", "EXPERIENCE_LEDGER", "RIFF_ARTIFACT", "MANUAL"}:
        raise ProfileValidationError("invalid evidence level, visibility, or origin")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1 or not isinstance(description, str) or not description.strip():
        raise ProfileValidationError("confidence must be 0..1 and description is required")
    if attestation not in {"USER_ATTESTED", "EXTERNALLY_VERIFIED", "UNVERIFIED"}:
        raise ProfileValidationError("invalid attestation state")
    if visibility == "PUBLIC" and level == "PROFESSIONALLY_DEMONSTRATED_PRIVATE":
        raise ProfileValidationError("private professional evidence must be private")
    if origin == "EXPERIENCE_LEDGER" and (visibility != "PRIVATE" or attestation != "USER_ATTESTED"):
        raise ProfileValidationError("Experience Ledger entries are private user attestations")
    if origin == "RIFF_ARTIFACT" and level != "UNKNOWN":
        raise ProfileValidationError("Riff artifacts enter as UNKNOWN candidate evidence")


def _evidence(row) -> ProfileEvidence:
    return ProfileEvidence(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]), float(row[5]), _text(row[6]), _text(row[7]), row[8], _text(row[9]), _text(row[10]), _text(row[11]))


def _assessment(row) -> GapAssessment:
    return GapAssessment(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _json(row[4]), _json(row[5]), row[6])


def _state(row) -> dict[str, Any]:
    if row is None:
        return {}
    return {"profile_evidence_id": _text(row[0]), "capability_id": _text(row[1]), "evidence_level": _text(row[2]), "visibility": _text(row[3]), "origin": _text(row[4]), "confidence": float(row[5]), "description": _text(row[6]), "reference": _text(row[7]), "status": _text(row[9]), "source_evidence_id": _text(row[10]), "attestation_state": _text(row[11])}


def _json(value):
    if isinstance(value, (bytes, str)):
        return json.loads(value.decode() if isinstance(value, bytes) else value)
    return value


def _text(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value
