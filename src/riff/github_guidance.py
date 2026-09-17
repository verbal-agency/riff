"""Deterministic GitHub project deltas, guidance, and bounded memory (G36)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection

PARSER_VERSION = "github-guidance-v1"
POLICY_VERSION = "github-guidance-policy-v1"
GUIDANCE_ACTIONS = {"EXTEND_PROJECT", "BUILD_GREENFIELD", "INVESTIGATE_GAP", "WAIT_FOR_EVIDENCE"}
DELTA_STATUSES = {"NEW", "CHANGED", "UNCHANGED", "DUPLICATE", "UNAVAILABLE"}
FEEDBACK_DECISIONS = {"ACCEPTED", "REJECTED", "DEFERRED", "CORRECTED"}


class GuidanceError(ValueError):
    """A bounded guidance or memory operation is invalid."""


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode()
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _claims(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = summary.get("claims", [])
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, Mapping)]


def project_delta(
    previous_summary: Mapping[str, Any] | None,
    current_summary: Mapping[str, Any] | None,
    *,
    current_snapshot_id: str,
    previous_snapshot_id: str | None = None,
    source_evidence_ids: Sequence[str] = (),
    retrieved_at: datetime | None = None,
    parser_version: str = PARSER_VERSION,
    policy_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    """Compare bounded G26 claims without interpreting raw repository code."""

    if not _text(current_snapshot_id):
        raise GuidanceError("current_snapshot_id is required")
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    if current_summary is None:
        status = "UNAVAILABLE"
        changed, unknown = [], [{"kind": "unknown", "value": "project_snapshot", "status": "UNKNOWN", "evidence_ids": []}]
    else:
        current = _claims(current_summary)
        prior = _claims(previous_summary or {})
        prior_keys = {(item.get("kind"), json.dumps(item.get("value"), sort_keys=True, default=str)) for item in prior}
        current_keys = {(item.get("kind"), json.dumps(item.get("value"), sort_keys=True, default=str)) for item in current}
        changed = [item for item in current if (item.get("kind"), json.dumps(item.get("value"), sort_keys=True, default=str)) not in prior_keys]
        removed = [item for item in prior if (item.get("kind"), json.dumps(item.get("value"), sort_keys=True, default=str)) not in current_keys]
        if not previous_summary:
            status = "NEW"
        elif not changed and not removed:
            prior_evidence = {e for item in prior for e in item.get("evidence_ids", [])}
            current_evidence = {e for item in current for e in item.get("evidence_ids", [])}
            status = "DUPLICATE" if current_evidence and current_evidence <= prior_evidence else "UNCHANGED"
        else:
            status = "CHANGED"
        unknown = [item for item in current if str(item.get("status", "")).upper() == "UNKNOWN"]
    claims = {"added": changed, "removed": removed if current_summary is not None else [], "unknown": unknown}
    evidence = sorted(set(str(value) for value in source_evidence_ids if str(value).strip()) | {str(e) for item in changed + unknown for e in item.get("evidence_ids", [])})
    uncertainty = []
    if unknown:
        uncertainty.append("bounded_snapshot_cannot_establish_implementation_depth")
    if status == "DUPLICATE":
        uncertainty.append("evidence_repeats_prior_snapshot")
    fingerprint = _hash({"current_snapshot_id": current_snapshot_id, "previous_snapshot_id": previous_snapshot_id, "claims": claims, "evidence": evidence, "parser_version": parser_version, "policy_version": policy_version})
    return {"status": status, "claims": claims, "source_evidence_ids": evidence, "uncertainty": uncertainty, "current_snapshot_id": current_snapshot_id, "previous_snapshot_id": previous_snapshot_id, "retrieved_at": retrieved_at.isoformat(), "parser_version": parser_version, "policy_version": policy_version, "input_fingerprint": fingerprint}


def rank_guidance(delta: Mapping[str, Any], *, project: Mapping[str, Any], profile: Mapping[str, Any] | None = None, decisions: Sequence[Mapping[str, Any]] = (), opportunity: Mapping[str, Any] | None = None, policy_version: str = POLICY_VERSION) -> dict[str, Any]:
    """Rank at most three typed actions from bounded facts and user context."""

    status = _text(delta.get("status"))
    claims = delta.get("claims", {}) if isinstance(delta.get("claims"), Mapping) else {}
    added = claims.get("added", []) if isinstance(claims.get("added", []), list) else []
    unknown = claims.get("unknown", []) if isinstance(claims.get("unknown", []), list) else []
    evidence = sorted(set(str(value) for value in delta.get("source_evidence_ids", []) if str(value).strip()))
    purpose = _text(project.get("purpose") or project.get("display_name"))
    actions: list[dict[str, Any]] = []
    if status in {"UNAVAILABLE", "UNCHANGED", "DUPLICATE"}:
        actions.append({"action_type": "WAIT_FOR_EVIDENCE", "score": 0.7 if status == "UNAVAILABLE" else 0.45, "rationale": "No new independently observable project change is available.", "evidence_ids": evidence, "uncertainty": list(delta.get("uncertainty", []))})
    if unknown:
        actions.append({"action_type": "INVESTIGATE_GAP", "score": 0.85, "rationale": "The bounded project map leaves an implementation-depth or surface unknown that should be tested directly.", "evidence_ids": sorted(set(evidence) | {str(e) for item in unknown for e in item.get("evidence_ids", [])}), "uncertainty": ["unknown_project_surface"]})
    seams = [item for item in added if str(item.get("kind")) in {"open_issue", "extension_seam"}]
    if seams and purpose:
        actions.append({"action_type": "EXTEND_PROJECT", "score": 0.9, "rationale": f"A changed project seam is relevant to {purpose}; extend only after validating the observed claim.", "evidence_ids": sorted(set(evidence) | {str(e) for item in seams for e in item.get("evidence_ids", [])}), "uncertainty": ["ownership_is_not_capability_proof"]})
    if status in {"NEW", "CHANGED"}:
        actions.append({"action_type": "BUILD_GREENFIELD", "score": 0.55, "rationale": "Keep a greenfield demonstration as a comparison when the project seam is not yet validated.", "evidence_ids": evidence, "uncertainty": ["project_fit_requires_user_judgment"]})
    actions = sorted(actions, key=lambda item: (-float(item["score"]), item["action_type"]))[:3]
    return {"policy_version": policy_version, "actions": actions, "project_id": project.get("project_id"), "delta_status": status, "cited_evidence_ids": sorted(set(evidence) | {str(e) for item in actions for e in item.get("evidence_ids", [])}), "uncertainty": sorted(set(str(v) for v in delta.get("uncertainty", [])) | {str(v) for item in actions for v in item.get("uncertainty", [])}), "context": {"profile_used": bool(profile), "decision_count": min(len(decisions), 20), "opportunity_used": bool(opportunity)}}


class GitHubGuidanceRepository:
    """Persist delta/guidance versions and append-only user feedback."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def resolve_project(self, reference: str) -> dict[str, Any]:
        value = _text(reference)
        if not value:
            raise GuidanceError("project reference is required")
        with connection(self.database_url) as conn:
            rows = conn.execute("""SELECT i.project_id,i.provider_repository_id,i.display_name,i.purpose,i.status,r.owner_login,r.name,r.canonical_url
                FROM github_project_inventory i JOIN github_repositories r USING (provider_repository_id)
                WHERE i.project_id=%s OR lower(i.display_name)=lower(%s) OR i.provider_repository_id=%s
                   OR lower(r.owner_login||'/'||r.name)=lower(%s) OR lower(r.canonical_url)=lower(%s)""", (value, value, value, value, value)).fetchall()
        if not rows:
            raise GuidanceError("project not found")
        if len(rows) > 1:
            choices = sorted({_text(row[5]) + "/" + _text(row[6]) for row in rows})[:5]
            raise GuidanceError("project reference is ambiguous; choose one of: " + ", ".join(choices))
        return {"project_id": _text(rows[0][0]), "provider_repository_id": _text(rows[0][1]), "display_name": _text(rows[0][2]), "purpose": _text(rows[0][3]) or None, "status": _text(rows[0][4]), "repository": _text(rows[0][5]) + "/" + _text(rows[0][6]), "canonical_url": _text(rows[0][7])}

    def _snapshots(self, project_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT snapshot_id,summary,source_evidence_ids FROM github_project_snapshots WHERE project_id=%s ORDER BY version DESC LIMIT 2", (project_id,)).fetchall()
        current = {"snapshot_id": _text(rows[0][0]), "summary": _json(rows[0][1], {}), "source_evidence_ids": _json(rows[0][2], [])} if rows else None
        previous = {"snapshot_id": _text(rows[1][0]), "summary": _json(rows[1][1], {}), "source_evidence_ids": _json(rows[1][2], [])} if len(rows) > 1 else None
        return current, previous

    def analyze(
        self,
        project: str,
        *,
        profile: Mapping[str, Any] | None = None,
        decisions: Sequence[Mapping[str, Any]] = (),
        opportunity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        project_row = self.resolve_project(project)
        current, previous = self._snapshots(project_row["project_id"])
        if current is None:
            raise GuidanceError("project has no persisted snapshot; refresh G26 before guidance")
        else:
            delta = project_delta(previous["summary"] if previous else None, current["summary"], current_snapshot_id=current["snapshot_id"], previous_snapshot_id=previous["snapshot_id"] if previous else None, source_evidence_ids=current["source_evidence_ids"])
        delta_id = "github-delta-" + delta["input_fingerprint"][:24]
        with connection(self.database_url) as conn:
            conn.execute("INSERT INTO github_guidance_deltas (delta_id,project_id,current_snapshot_id,previous_snapshot_id,status,claims,source_evidence_ids,uncertainty,parser_version,policy_version,input_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (input_fingerprint) DO NOTHING", (delta_id, project_row["project_id"], delta["current_snapshot_id"], delta.get("previous_snapshot_id"), delta["status"], Jsonb(delta["claims"]), Jsonb(delta["source_evidence_ids"]), Jsonb(delta["uncertainty"]), delta["parser_version"], delta["policy_version"], delta["input_fingerprint"]))
        guidance = rank_guidance(
            delta,
            project=project_row,
            profile=profile,
            decisions=decisions,
            opportunity=opportunity,
        )
        guidance_fp = _hash({"delta": delta["input_fingerprint"], "guidance": guidance, "policy_version": POLICY_VERSION})
        guidance_id = "github-guidance-" + guidance_fp[:24]
        with connection(self.database_url) as conn:
            prior = conn.execute("SELECT guidance_id,version FROM github_guidance_versions WHERE project_id=%s ORDER BY version DESC LIMIT 1", (project_row["project_id"],)).fetchone()
            conn.execute("INSERT INTO github_guidance_versions (guidance_id,project_id,delta_id,prior_guidance_id,version,actions,rationale,cited_evidence_ids,uncertainty,policy_version,input_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (input_fingerprint) DO NOTHING", (guidance_id, project_row["project_id"], delta_id, _text(prior[0]) if prior else None, int(prior[1]) + 1 if prior else 1, Jsonb(guidance["actions"]), "Deterministic guidance from bounded project delta and context.", Jsonb(guidance["cited_evidence_ids"]), Jsonb(guidance["uncertainty"]), POLICY_VERSION, guidance_fp))
        return {"project": project_row, "delta": {**delta, "delta_id": delta_id}, "guidance": {**guidance, "guidance_id": guidance_id, "input_fingerprint": guidance_fp}}

    def feedback(self, guidance_id: str, decision: str, reason: str, *, correction: Mapping[str, Any] | None = None, actor: str = "user") -> dict[str, Any]:
        if decision not in FEEDBACK_DECISIONS or not _text(reason) or not _text(actor):
            raise GuidanceError("feedback requires a valid decision, reason, and actor")
        feedback_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            if conn.execute("SELECT 1 FROM github_guidance_versions WHERE guidance_id=%s", (_text(guidance_id),)).fetchone() is None:
                raise GuidanceError("guidance not found")
            conn.execute("INSERT INTO github_guidance_feedback (feedback_id,guidance_id,decision,reason,correction,actor,policy_version) VALUES (%s,%s,%s,%s,%s,%s,%s)", (feedback_id, guidance_id, decision, reason.strip(), Jsonb(dict(correction or {})), actor.strip(), POLICY_VERSION))
        return {"feedback_id": feedback_id, "guidance_id": guidance_id, "decision": decision, "reason": reason.strip(), "policy_version": POLICY_VERSION}

    def audit(self, project: str, *, limit: int = 10) -> dict[str, Any]:
        project_row = self.resolve_project(project)
        with connection(self.database_url) as conn:
            guidance = conn.execute("SELECT guidance_id,version,delta_id,actions,cited_evidence_ids,uncertainty,policy_version,created_at FROM github_guidance_versions WHERE project_id=%s ORDER BY version DESC LIMIT %s", (project_row["project_id"], min(max(limit, 1), 20))).fetchall()
            feedback = conn.execute("SELECT f.feedback_id,f.guidance_id,f.decision,f.reason,f.actor,f.created_at FROM github_guidance_feedback f JOIN github_guidance_versions g ON g.guidance_id=f.guidance_id WHERE g.project_id=%s ORDER BY f.created_at DESC LIMIT %s", (project_row["project_id"], min(max(limit, 1), 20))).fetchall()
        return {"project": project_row, "guidance_versions": [{"guidance_id": _text(row[0]), "version": int(row[1]), "delta_id": _text(row[2]), "actions": _json(row[3], []), "cited_evidence_ids": _json(row[4], []), "uncertainty": _json(row[5], []), "policy_version": _text(row[6]), "created_at": row[7].isoformat()} for row in guidance], "feedback": [{"feedback_id": _text(row[0]), "guidance_id": _text(row[1]), "decision": _text(row[2]), "reason": _text(row[3]), "actor": _text(row[4]), "created_at": row[5].isoformat()} for row in feedback], "memory_layers": ["evidence_ledger", "project_understanding", "user_decision_memory", "guidance_memory", "conversation_context"]}
