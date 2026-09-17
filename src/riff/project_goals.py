"""Bounded, evidence-backed project-goal projections (G37).

Goals are deliberately extracted only from explicit roadmap/goal language in
the already-ingested GitHub artifacts.  This module never treats repository
ownership, filenames, activity, or model prose as a goal.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection

PARSER_VERSION = "github-project-goals-v1"
POLICY_VERSION = "github-project-goals-policy-v1"
GOAL_STATUSES = {"ACTIVE", "COMPLETED", "ARCHIVED", "UNKNOWN"}
EVIDENCE_STATUSES = {"OBSERVED", "INFERRED", "UNKNOWN"}
DECISION_EVENTS = {"PRIORITIZED", "COMPLETED", "ARCHIVED", "CORRECTED", "REACTIVATED"}


class ProjectGoalError(ValueError):
    pass


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    return str(value or "").strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _status(text: str) -> str:
    value = text.lower()
    if re.search(r"\b(done|complete|completed|shipped|delivered)\b", value):
        return "COMPLETED"
    if re.search(r"\b(archived|deprecated|dropped)\b", value):
        return "ARCHIVED"
    if re.search(r"\b(active|in progress|underway|current)\b", value):
        return "ACTIVE"
    return "UNKNOWN"


def extract_goals(
    project: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    *,
    snapshot_id: str | None = None,
    observed_at: datetime | None = None,
    parser_version: str = PARSER_VERSION,
    policy_version: str = POLICY_VERSION,
) -> list[dict[str, Any]]:
    """Extract at most ten explicit goals from bounded artifact text."""
    project_id = _text(project.get("project_id"))
    if not project_id:
        raise ProjectGoalError("project_id is required")
    observed_at = observed_at or _now()
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    results: list[dict[str, Any]] = []
    # Headings and list items must contain explicit goal vocabulary.  This
    # prevents README filenames or arbitrary prose from becoming goals.
    pattern = re.compile(r"^\s*(?:#{1,6}\s*|[-*]\s+|\d+[.)]\s+)?(?P<body>(?:(?:goal|milestone|roadmap|next\s+step|todo|to-do)\b|ma-\d+\b).*)$", re.I)
    for artifact in artifacts:
        evidence_id = _text(artifact.get("evidence_id"))
        if not evidence_id:
            continue
        source_surface = _text(artifact.get("artifact_type")) or "UNKNOWN"
        title = _text(artifact.get("title"))
        content = _text(artifact.get("content", artifact.get("raw_content", "")))
        lines = ([title] if title else []) + content.splitlines()[:400]
        for line in lines:
            match = pattern.match(line)
            if not match:
                continue
            body = re.sub(r"\s+", " ", match.group("body")).strip(" -:")
            if len(body) < 8 or len(body) > 280:
                continue
            status = _status(body)
            normalized = re.sub(r"[^a-z0-9]+", "-", body.lower()).strip("-")
            identifier = re.match(r"(?:goal|milestone)\s+([a-z0-9-]+)", body, re.I) or re.match(r"(ma-\d+)", body, re.I)
            stable = identifier.group(1).lower() if identifier else "-".join(normalized.split("-")[:4])
            goal_key = _hash({"project_id": project_id, "title": stable})[:32]
            candidate = {
                "project_id": project_id,
                "goal_key": goal_key,
                "title": body,
                "status": status,
                "evidence_status": "OBSERVED",
                "source_surface": source_surface,
                "source_evidence_ids": [evidence_id],
                "source_urls": [_text(artifact.get("canonical_url"))] if _text(artifact.get("canonical_url")) else [],
                "observed_at": observed_at.isoformat(),
                "snapshot_id": _text(snapshot_id) or None,
                "parser_version": parser_version,
                "policy_version": policy_version,
            }
            candidate["input_fingerprint"] = _hash(candidate)
            if not any(item["goal_key"] == goal_key for item in results):
                results.append(candidate)
        if len(results) >= 10:
            break
    return results


def rank_goal_guidance(
    goal: Mapping[str, Any],
    *,
    delta: Mapping[str, Any],
    project: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
    decisions: Sequence[Mapping[str, Any]] = (),
    opportunity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a bounded comparison of paths for one selected goal."""
    goal_id = _text(goal.get("goal_version_id") or goal.get("goal_key"))
    goal_evidence = {_text(item) for item in goal.get("source_evidence_ids", []) if _text(item)}
    delta_evidence = {_text(item) for item in delta.get("source_evidence_ids", []) if _text(item)}
    cited = sorted(goal_evidence | delta_evidence)
    unknown = list(delta.get("uncertainty", []))
    if goal.get("status") == "UNKNOWN":
        unknown.append("goal_status_is_unknown")
    synthetic = bool(goal.get("synthetic") or goal.get("data_origin") in {"FIXTURE", "TEST"})
    if synthetic:
        unknown.append("goal_or_evidence_is_synthetic")
    actions: list[dict[str, Any]] = []
    if not cited or synthetic or str(delta.get("status")) == "UNAVAILABLE":
        actions.append({"action_type": "INVESTIGATE_GAP", "score": 0.82, "rationale": "Validate the selected goal and gather credible evidence before claiming project fit.", "effort_hours": {"min": 2, "max": 6}, "goal_key": goal_id, "evidence_ids": cited, "uncertainty": sorted(set(unknown or ["insufficient_evidence"]))})
        actions.append({"action_type": "WAIT_FOR_EVIDENCE", "score": 0.55, "rationale": "Keep the direction open until an independent project or capability receipt arrives.", "effort_hours": {"min": 1, "max": 2}, "goal_key": goal_id, "evidence_ids": cited, "uncertainty": sorted(set(unknown or ["insufficient_evidence"]))})
    else:
        claims = delta.get("claims", {}) if isinstance(delta.get("claims"), Mapping) else {}
        seams = claims.get("added", []) if isinstance(claims.get("added", []), list) else []
        has_seam = any(str(item.get("kind")) in {"open_issue", "extension_seam"} for item in seams if isinstance(item, Mapping))
        if has_seam:
            actions.append({"action_type": "EXTEND_PROJECT", "score": 0.86, "rationale": "The selected goal has an observed project seam; validate it with a narrow extension.", "effort_hours": {"min": 4, "max": 12}, "goal_key": goal_id, "evidence_ids": cited, "uncertainty": sorted(set(unknown + ["ownership_is_not_capability_proof"]))})
        actions.append({"action_type": "BUILD_GREENFIELD", "score": 0.62 if has_seam else 0.78, "rationale": "Build a bounded comparison artifact so project fit and distinctiveness are tested rather than assumed.", "effort_hours": {"min": 4, "max": 10}, "goal_key": goal_id, "evidence_ids": cited, "uncertainty": sorted(set(unknown + ["project_fit_requires_user_judgment"]))})
        if str(delta.get("status")) in {"UNCHANGED", "DUPLICATE"}:
            actions.append({"action_type": "WAIT_FOR_EVIDENCE", "score": 0.42, "rationale": "No new project change is observable for this goal; avoid overfitting to stale context.", "effort_hours": {"min": 1, "max": 2}, "goal_key": goal_id, "evidence_ids": cited, "uncertainty": sorted(set(unknown + ["stale_project_delta"]))})
    actions = sorted(actions, key=lambda item: (-float(item["score"]), item["action_type"]))[:3]
    return {"policy_version": POLICY_VERSION, "goal": dict(goal), "project_id": project.get("project_id"), "actions": actions, "cited_evidence_ids": cited, "uncertainty": sorted(set(unknown)), "context": {"profile_used": bool(profile), "decision_count": min(len(decisions), 20), "opportunity_used": bool(opportunity)}}


class ProjectGoalRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def resolve_project(self, reference: str) -> dict[str, Any]:
        value = _text(reference).rstrip("/")
        if not value:
            raise ProjectGoalError("project reference is required")
        with connection(self.database_url) as conn:
            rows = conn.execute("""SELECT i.project_id,i.provider_repository_id,i.display_name,i.purpose,i.status,r.owner_login,r.name,r.canonical_url
                FROM github_project_inventory i JOIN github_repositories r USING (provider_repository_id)
                WHERE i.project_id=%s OR lower(i.display_name)=lower(%s) OR i.provider_repository_id=%s
                   OR lower(r.owner_login||'/'||r.name)=lower(%s) OR lower(r.canonical_url)=lower(%s)""", (value, value, value, value, value)).fetchall()
        if not rows:
            raise ProjectGoalError("project not found")
        if len(rows) > 1:
            choices = sorted({_text(row[5]) + "/" + _text(row[6]) for row in rows})[:5]
            raise ProjectGoalError("project reference is ambiguous; choose one of: " + ", ".join(choices))
        row = rows[0]
        return {"project_id": _text(row[0]), "provider_repository_id": _text(row[1]), "display_name": _text(row[2]), "purpose": _text(row[3]) or None, "status": _text(row[4]), "repository": _text(row[5]) + "/" + _text(row[6]), "canonical_url": _text(row[7])}

    def _artifacts(self, project: Mapping[str, Any]) -> list[dict[str, Any]]:
        with connection(self.database_url) as conn:
            rows = conn.execute("""SELECT ga.evidence_id,ga.artifact_type,ga.canonical_url,ga.observed_at,si.title,e.raw_content
                FROM github_artifacts ga JOIN evidence_versions e USING (evidence_id) JOIN source_items si USING (source_item_id)
                WHERE ga.provider_repository_id=%s ORDER BY ga.observed_at DESC,ga.provider_artifact_id DESC LIMIT 200""", (project["provider_repository_id"],)).fetchall()
        return [{"evidence_id": _text(r[0]), "artifact_type": _text(r[1]), "canonical_url": _text(r[2]), "observed_at": r[3], "title": _text(r[4]), "content": _text(r[5])} for r in rows]

    def persist(self, project: Mapping[str, Any], snapshot_id: str | None, goals: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        project_id = _text(project.get("project_id"))
        if not project_id:
            raise ProjectGoalError("project_id is required")
        output: list[dict[str, Any]] = []
        with connection(self.database_url) as conn:
            for goal in goals[:10]:
                key, fp = _text(goal.get("goal_key")), _text(goal.get("input_fingerprint"))
                if not key or not fp:
                    continue
                existing = conn.execute("SELECT goal_version_id,version FROM github_project_goal_versions WHERE project_id=%s AND goal_key=%s AND input_fingerprint=%s", (project_id, key, fp)).fetchone()
                if existing:
                    row = conn.execute("SELECT * FROM github_project_goal_versions WHERE goal_version_id=%s", (existing[0],)).fetchone()
                    output.append(self._row(row)); continue
                prior = conn.execute("SELECT goal_version_id,version FROM github_project_goal_versions WHERE project_id=%s AND goal_key=%s ORDER BY version DESC LIMIT 1", (project_id, key)).fetchone()
                gid = "github-goal-" + str(uuid.uuid4())
                version = int(prior[1]) + 1 if prior else 1
                conn.execute("""INSERT INTO github_project_goal_versions (goal_version_id,project_id,snapshot_id,goal_key,version,title,status,evidence_status,source_surface,source_evidence_ids,source_urls,observed_at,parser_version,policy_version,input_fingerprint,prior_goal_version_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (gid, project_id, snapshot_id, key, version, _text(goal.get("title")), _text(goal.get("status")) or "UNKNOWN", _text(goal.get("evidence_status")) or "UNKNOWN", _text(goal.get("source_surface")) or "UNKNOWN", Jsonb(list(goal.get("source_evidence_ids", []))), Jsonb(list(goal.get("source_urls", []))), goal.get("observed_at") or _now(), _text(goal.get("parser_version")) or PARSER_VERSION, _text(goal.get("policy_version")) or POLICY_VERSION, fp, _text(prior[0]) if prior else None))
                row = conn.execute("SELECT * FROM github_project_goal_versions WHERE goal_version_id=%s", (gid,)).fetchone()
                output.append(self._row(row))
        return output

    def refresh(self, project: str) -> dict[str, Any]:
        resolved = self.resolve_project(project)
        with connection(self.database_url) as conn:
            snap = conn.execute("SELECT snapshot_id FROM github_project_snapshots WHERE project_id=%s ORDER BY version DESC LIMIT 1", (resolved["project_id"],)).fetchone()
        snapshot_id = _text(snap[0]) if snap else None
        goals = extract_goals(resolved, self._artifacts(resolved), snapshot_id=snapshot_id)
        return {"project": resolved, "snapshot_id": snapshot_id, "goals": self.persist(resolved, snapshot_id, goals), "goal_count": len(goals)}

    def list(self, project: str, limit: int = 10) -> dict[str, Any]:
        resolved = self.resolve_project(project)
        with connection(self.database_url) as conn:
            rows = conn.execute("""SELECT DISTINCT ON (goal_key) * FROM github_project_goal_versions WHERE project_id=%s ORDER BY goal_key,version DESC LIMIT %s""", (resolved["project_id"], min(max(limit, 1), 10))).fetchall()
        return {"project": resolved, "goals": [self._row(row) for row in rows]}

    def get_goal(self, project: str, goal: str) -> dict[str, Any]:
        resolved = self.resolve_project(project); needle = _text(goal)
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT * FROM github_project_goal_versions WHERE project_id=%s AND (goal_version_id=%s OR goal_key=%s OR lower(title)=lower(%s)) ORDER BY version DESC LIMIT 10", (resolved["project_id"], needle, needle, needle)).fetchall()
        if not rows: raise ProjectGoalError("goal not found; refresh the project goals first")
        keys = {_text(row[3]) for row in rows}
        if len(keys) > 1: raise ProjectGoalError("goal reference is ambiguous; use its title with more context")
        return self._row(rows[0])

    def record_decision(self, goal_version_id: str, event_type: str, reason: str, *, confirmation_token: str, actor: str = "user") -> dict[str, Any]:
        if confirmation_token != "USER_CONFIRMED": raise ProjectGoalError("goal decisions require USER_CONFIRMED")
        if event_type not in DECISION_EVENTS or not _text(reason): raise ProjectGoalError("event_type and reason are required")
        event_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT project_id FROM github_project_goal_versions WHERE goal_version_id=%s", (_text(goal_version_id),)).fetchone()
            if not row: raise ProjectGoalError("goal version not found")
            conn.execute("INSERT INTO github_project_goal_events (event_id,project_id,goal_version_id,event_type,payload,reason,actor,policy_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (event_id, row[0], goal_version_id, event_type, Jsonb({}), reason.strip(), actor.strip() or "user", POLICY_VERSION))
        return {"event_id": event_id, "goal_version_id": goal_version_id, "event_type": event_type, "reason": reason.strip(), "policy_version": POLICY_VERSION}

    @staticmethod
    def _row(row: Sequence[Any]) -> dict[str, Any]:
        names = ["goal_version_id","project_id","snapshot_id","goal_key","version","title","status","evidence_status","source_surface","source_evidence_ids","source_urls","observed_at","parser_version","policy_version","input_fingerprint","prior_goal_version_id","created_at"]
        value = dict(zip(names, row)); value["source_evidence_ids"] = value.get("source_evidence_ids") or []; value["source_urls"] = value.get("source_urls") or []
        for key in ("observed_at", "created_at"):
            if hasattr(value.get(key), "isoformat"): value[key] = value[key].isoformat()
        return value
