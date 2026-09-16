"""Deterministic, provenance-aware recommendations for extending GitHub projects (G27)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection
from .decisions import DecisionRepository
from .explorations import ExplorationRepository
from .project_map import ProjectMapError, ProjectMapRepository


POLICY_VERSION = "recommendation-policy-v1"
DISPOSITIONS = {"EXTEND_EXISTING", "START_NEW", "NOT_NOW"}
STATUSES = {"PROPOSED", "OVERRIDDEN", "ACCEPTED", "DEFERRED"}
_STOP_WORDS = {"a", "an", "and", "as", "for", "from", "in", "into", "of", "on", "the", "to", "with"}


class RecommendationError(ValueError):
    """Raised when a recommendation cannot be safely generated or transitioned."""


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: str
    riff_id: str
    project_id: str | None
    disposition: str
    fit_score: float
    learning_value: float
    effort_hours: float
    scope_risk: float
    confidence: float
    evidence_ids: tuple[str, ...]
    project_snapshot_id: str | None
    rationale: str
    uncertainty: dict[str, Any]
    policy_version: str
    status: str = "PROPOSED"
    extension_seam: str | None = None
    project_name: str | None = None
    signal_evidence_ids: tuple[str, ...] = ()
    project_evidence_ids: tuple[str, ...] = ()
    override_disposition: str | None = None
    override_reason: str | None = None
    input_fingerprint: str = ""
    created_at: Any = None
    updated_at: Any = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence_ids"] = list(self.evidence_ids)
        value["signal_evidence_ids"] = list(self.signal_evidence_ids)
        value["project_evidence_ids"] = list(self.project_evidence_ids)
        value["effective_disposition"] = self.override_disposition or self.disposition
        return value


def _text(value: Any) -> str:
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


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+._-]{1,}", _text(value).lower())
        if token not in _STOP_WORDS
    }


def _values(summary: Mapping[str, Any], key: str) -> list[str]:
    values = summary.get(key, [])
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            value = item.get("value")
        else:
            value = item
        if _text(value):
            result.append(_text(value))
    return result


def _seam(summary: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    values = summary.get("extension_seams", [])
    if not isinstance(values, list):
        return None, []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        value = _text(item.get("value"))
        status = _text(item.get("status"))
        if value and status != "UNKNOWN":
            return value, [_text(item.get("evidence_ids"))] if isinstance(item.get("evidence_ids"), str) else [str(v) for v in item.get("evidence_ids", [])]
    return None, []


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return round(len(left & right) / max(1, len(left)), 4)


def _recommendation(
    *,
    riff_id: str,
    disposition: str,
    project_id: str | None,
    project_name: str | None,
    project_snapshot_id: str | None,
    fit_score: float,
    learning_value: float,
    effort_hours: float,
    scope_risk: float,
    confidence: float,
    signal_evidence_ids: Sequence[str],
    project_evidence_ids: Sequence[str],
    extension_seam: str | None,
    rationale: str,
    uncertainty: Mapping[str, Any],
) -> Recommendation:
    signal_ids = tuple(sorted({_text(item) for item in signal_evidence_ids if _text(item)}))
    project_ids = tuple(sorted({_text(item) for item in project_evidence_ids if _text(item)}))
    evidence_ids = tuple(dict.fromkeys((*signal_ids, *project_ids)))[:10]
    payload = {
        "riff_id": riff_id,
        "project_id": project_id,
        "project_snapshot_id": project_snapshot_id,
        "disposition": disposition,
        "fit_score": round(max(0.0, min(1.0, fit_score)), 4),
        "learning_value": round(max(0.0, min(1.0, learning_value)), 4),
        "effort_hours": round(max(4.0, min(20.0, effort_hours)), 2),
        "scope_risk": round(max(0.0, min(1.0, scope_risk)), 4),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "evidence_ids": evidence_ids,
        "rationale": rationale,
        "uncertainty": dict(uncertainty),
        "policy_version": POLICY_VERSION,
        "extension_seam": extension_seam,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    recommendation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"riff-recommendation:{fingerprint}"))
    return Recommendation(
        recommendation_id,
        riff_id,
        project_id,
        disposition,
        payload["fit_score"],
        payload["learning_value"],
        payload["effort_hours"],
        payload["scope_risk"],
        payload["confidence"],
        evidence_ids,
        project_snapshot_id,
        rationale,
        dict(uncertainty),
        POLICY_VERSION,
        "PROPOSED",
        extension_seam,
        project_name,
        signal_ids,
        project_ids,
        None,
        None,
        fingerprint,
    )


def build_recommendations(
    riff: Mapping[str, Any],
    projects: Sequence[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> list[Recommendation]:
    """Match a Riff to bounded project summaries without network or model calls."""

    if not 1 <= limit <= 5:
        raise RecommendationError("limit must be between 1 and 5")
    riff_id = _text(riff.get("riff_id"))
    if not riff_id:
        raise RecommendationError("riff_id is required")
    capability = _text(riff.get("underlying_capability"))
    technologies = [_text(item) for item in riff.get("associated_technologies", []) if _text(item)]
    signal_ids = [
        _text(item.get("evidence_id")) if isinstance(item, Mapping) else _text(item)
        for item in riff.get("evidence_ids", riff.get("supporting_evidence_ids", []))
    ]
    signal_ids = [item for item in signal_ids if item]
    signal_text = " ".join(_text(riff.get(key)) for key in ("underlying_capability", "hypothesis", "recommendation"))
    signal_tokens = _tokens(signal_text)
    actionable = bool(capability and signal_ids)
    matches: list[Recommendation] = []
    for project in projects[:5]:
        project_id = _text(project.get("project_id"))
        if not project_id:
            continue
        summary = project.get("summary") if isinstance(project.get("summary"), Mapping) else {}
        project_name = _text(project.get("display_name")) or _text(summary.get("display_name")) or project_id
        status = _text(project.get("status")).upper()
        snapshot_id = _text(project.get("snapshot_id")) or None
        project_evidence = [
            _text(item) for item in _json(project.get("source_evidence_ids"), []) if _text(item)
        ]
        capabilities = _values(summary, "capabilities")
        project_technologies = _values(summary, "technologies")
        purposes = _values(summary, "purpose")
        seams, seam_evidence = _seam(summary)
        project_evidence.extend(seam_evidence)
        cap_score = max((_overlap(_tokens(capability), _tokens(value)) for value in capabilities), default=0.0)
        tech_score = _overlap(_tokens(" ".join(technologies)), _tokens(" ".join(project_technologies)))
        text_score = _overlap(signal_tokens, _tokens(" ".join((*purposes, seams or ""))))
        seam_score = 0.85 if seams else 0.0
        health_score = 1.0 if status == "ACTIVE" and snapshot_id else 0.0
        fit = round(min(1.0, 0.45 * cap_score + 0.20 * tech_score + 0.20 * max(text_score, seam_score * cap_score) + 0.15 * health_score), 4)
        unknowns = [
            _text(item.get("value"))
            for item in summary.get("unknowns", [])
            if isinstance(item, Mapping) and _text(item.get("value"))
        ]
        missing = []
        if not snapshot_id:
            missing.append("a current project snapshot")
        if not seams:
            missing.append("a credible extension seam")
        if not signal_ids:
            missing.append("at least one cited Riff receipt")
        scope_risk = round(min(1.0, 0.20 + (0.15 if unknowns else 0.0) + (0.20 if not seams else 0.0) + (0.20 if fit < 0.35 else 0.0)), 4)
        learning = round(min(1.0, 0.55 + (0.25 if "gap" in _text(riff.get("user_relevance")).lower() else 0.0) + (0.15 if seams else 0.0)), 4)
        confidence = round(min(0.95, 0.30 + (0.20 if snapshot_id else 0.0) + (0.15 if signal_ids else 0.0) + (0.15 * cap_score) + (0.10 if seams else 0.0)), 4)
        if status != "ACTIVE" or not actionable:
            disposition = "NOT_NOW"
            project_ref = None
            rationale = f"Defer {project_name}: " + ("the Riff lacks a cited receipt." if not signal_ids else "the project is not an active, evidence-backed target.")
        elif snapshot_id and seams and fit >= 0.35:
            disposition = "EXTEND_EXISTING"
            project_ref = project_id
            rationale = f"Extend {project_name} at the observed seam '{seams}'; capability fit is {fit:.2f} and the project snapshot is current."
        else:
            disposition = "START_NEW"
            project_ref = None
            rationale = f"Start a separate project: {project_name} has no sufficiently credible bounded seam for this Riff."
        matches.append(_recommendation(
            riff_id=riff_id,
            disposition=disposition,
            project_id=project_ref,
            project_name=project_name,
            project_snapshot_id=snapshot_id if disposition == "EXTEND_EXISTING" else None,
            fit_score=fit,
            learning_value=learning,
            effort_hours=8.0 if seams else 12.0,
            scope_risk=scope_risk,
            confidence=confidence,
            signal_evidence_ids=signal_ids,
            project_evidence_ids=project_evidence,
            extension_seam=seams if disposition == "EXTEND_EXISTING" else None,
            rationale=rationale,
            uncertainty={"unknowns": unknowns, "missing_evidence": missing},
        ))
    extensions = sorted((item for item in matches if item.disposition == "EXTEND_EXISTING"), key=lambda item: (-item.fit_score, item.project_name or ""))
    if extensions:
        result = extensions[: max(1, limit - 1)]
        if actionable and len(result) < limit:
            result.append(_recommendation(
                riff_id=riff_id,
                disposition="START_NEW",
                project_id=None,
                project_name=None,
                project_snapshot_id=None,
                fit_score=0.0,
                learning_value=0.65,
                effort_hours=12.0,
                scope_risk=0.45,
                confidence=0.45,
                signal_evidence_ids=signal_ids,
                project_evidence_ids=(),
                extension_seam=None,
                rationale="Start a new project if no existing seam is worth constraining the experiment around.",
                uncertainty={"unknowns": [], "missing_evidence": ["a project seam that beats the greenfield alternative"]},
            ))
        return result[:limit]
    if actionable:
        return [
            _recommendation(
                riff_id=riff_id,
                disposition="START_NEW",
                project_id=None,
                project_name=None,
                project_snapshot_id=None,
                fit_score=0.0,
                learning_value=0.65,
                effort_hours=12.0,
                scope_risk=0.45,
                confidence=0.45,
                signal_evidence_ids=signal_ids,
                project_evidence_ids=(),
                extension_seam=None,
                rationale="Start a new project because no active project has a sufficiently credible extension seam.",
                uncertainty={"unknowns": [], "missing_evidence": ["a credible existing-project seam"]},
            )
        ][:limit]
    return [
        _recommendation(
            riff_id=riff_id,
            disposition="NOT_NOW",
            project_id=None,
            project_name=None,
            project_snapshot_id=None,
            fit_score=0.0,
            learning_value=0.0,
            effort_hours=8.0,
            scope_risk=0.65,
            confidence=0.20,
            signal_evidence_ids=(),
            project_evidence_ids=(),
            extension_seam=None,
            rationale="Defer this recommendation until the Riff has a cited receipt and a bounded project context.",
            uncertainty={"unknowns": [], "missing_evidence": ["at least one cited Riff receipt", "a bounded project snapshot"]},
        )
    ]


class RecommendationRepository:
    """Persist recommendation snapshots and explicit user overrides."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def _project_inputs(self, limit: int = 5, *, include_non_live: bool = False) -> list[dict[str, Any]]:
        if not 1 <= limit <= 5:
            raise RecommendationError("project limit must be between 1 and 5")
        with connection(self.database_url) as conn:
            rows = conn.execute(
                """
                SELECT i.project_id, i.display_name, i.status, s.snapshot_id,
                       s.source_evidence_ids, s.summary
                FROM github_project_inventory i
                LEFT JOIN LATERAL (
                    SELECT snapshot_id, source_evidence_ids, summary
                    FROM github_project_snapshots
                    WHERE project_id = i.project_id
                    ORDER BY version DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE i.review_status = 'APPROVED'
                  AND (%s OR COALESCE(i.data_origin, 'UNCLASSIFIED') NOT IN ('FIXTURE', 'TEST', 'QUARANTINED'))
                ORDER BY i.updated_at DESC, i.project_id
                LIMIT %s
                """,
                (include_non_live, limit),
            ).fetchall()
        return [
            {
                "project_id": _text(row[0]),
                "display_name": _text(row[1]),
                "status": _text(row[2]),
                "snapshot_id": _text(row[3]) or None,
                "source_evidence_ids": _json(row[4], []),
                "summary": _json(row[5], {}),
            }
            for row in rows
        ]

    def list_projects(self, *, limit: int = 5, include_non_live: bool = False) -> list[dict[str, Any]]:
        """Return bounded project summaries suitable for a conversational client."""

        return self._project_inputs(limit, include_non_live=include_non_live)

    def match_riff(self, riff_id: str, *, limit: int = 3) -> dict[str, Any]:
        investigation = DecisionRepository(self.database_url).investigation(riff_id)
        riff = dict(investigation.riff)
        riff["evidence_ids"] = [item.get("evidence_id") for item in investigation.supporting_evidence]
        recommendations = build_recommendations(riff, self._project_inputs(), limit=limit)
        with connection(self.database_url) as conn:
            for item in recommendations:
                conn.execute(
                    """
                    INSERT INTO project_recommendations
                    (recommendation_id, riff_id, project_id, disposition, fit_score,
                     learning_value, effort_hours, scope_risk, confidence, evidence_ids,
                     project_snapshot_id, rationale, uncertainty, policy_version, status,
                     extension_seam, project_name, signal_evidence_ids, project_evidence_ids,
                     input_fingerprint)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'PROPOSED', %s, %s, %s, %s, %s)
                    ON CONFLICT (input_fingerprint) DO NOTHING
                    """,
                    (item.recommendation_id, item.riff_id, item.project_id, item.disposition,
                     item.fit_score, item.learning_value, item.effort_hours, item.scope_risk,
                     item.confidence, Jsonb(list(item.evidence_ids)), item.project_snapshot_id,
                     item.rationale, Jsonb(item.uncertainty), item.policy_version,
                     item.extension_seam, item.project_name, Jsonb(list(item.signal_evidence_ids)),
                     Jsonb(list(item.project_evidence_ids)), item.input_fingerprint),
                )
        return {"riff_id": riff_id, "policy_version": POLICY_VERSION, "recommendations": [self.get(item.recommendation_id).to_dict() for item in recommendations]}

    def get(self, recommendation_id: str) -> Recommendation:
        with connection(self.database_url) as conn:
            row = conn.execute(
                """
                SELECT recommendation_id, riff_id, project_id, disposition, fit_score,
                       learning_value, effort_hours, scope_risk, confidence, evidence_ids,
                       project_snapshot_id, rationale, uncertainty, policy_version, status,
                       extension_seam, project_name, signal_evidence_ids, project_evidence_ids,
                       override_disposition, override_reason, input_fingerprint, created_at,
                       updated_at
                FROM project_recommendations WHERE recommendation_id = %s
                """,
                (recommendation_id,),
            ).fetchone()
        if row is None:
            raise RecommendationError("recommendation not found")
        return Recommendation(
            _text(row[0]), _text(row[1]), _text(row[2]) or None, _text(row[3]), float(row[4]),
            float(row[5]), float(row[6]), float(row[7]), float(row[8]), tuple(_json(row[9], [])),
            _text(row[10]) or None, _text(row[11]), dict(_json(row[12], {})), _text(row[13]),
            _text(row[14]), _text(row[15]) or None, _text(row[16]) or None,
            tuple(_json(row[17], [])), tuple(_json(row[18], [])), _text(row[19]) or None,
            _text(row[20]) or None, _text(row[21]), row[22], row[23],
        )

    def list_for_riff(self, riff_id: str, *, limit: int = 5) -> list[Recommendation]:
        if not 1 <= limit <= 5:
            raise RecommendationError("limit must be between 1 and 5")
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT recommendation_id FROM project_recommendations WHERE riff_id = %s ORDER BY created_at DESC LIMIT %s",
                (riff_id, limit),
            ).fetchall()
        return [self.get(_text(row[0])) for row in rows]

    def override(self, recommendation_id: str, disposition: str, reason: str) -> Recommendation:
        if disposition not in DISPOSITIONS or not _text(reason):
            raise RecommendationError("override requires a supported disposition and reason")
        current = self.get(recommendation_id)
        if current.status == "ACCEPTED":
            raise RecommendationError("an accepted recommendation cannot be overridden")
        with connection(self.database_url) as conn:
            conn.execute(
                "UPDATE project_recommendations SET status = 'OVERRIDDEN', override_disposition = %s, override_reason = %s, updated_at = now() WHERE recommendation_id = %s",
                (disposition, reason.strip(), recommendation_id),
            )
        return self.get(recommendation_id)

    def accept_extension(self, recommendation_id: str) -> dict[str, Any]:
        current = self.get(recommendation_id)
        disposition = current.override_disposition or current.disposition
        if disposition != "EXTEND_EXISTING" or not current.project_id:
            raise RecommendationError("only an extension recommendation can be accepted")
        with connection(self.database_url) as conn:
            project = conn.execute(
                "SELECT status, review_status FROM github_project_inventory WHERE project_id = %s",
                (current.project_id,),
            ).fetchone()
            approval = conn.execute(
                "SELECT 1 FROM riff_decisions WHERE riff_id = %s AND decision = 'APPROVE_EXPLORATION' AND actor_kind = 'USER' LIMIT 1",
                (current.riff_id,),
            ).fetchone()
        if project is None or _text(project[0]) != "ACTIVE" or _text(project[1]) != "APPROVED":
            raise RecommendationError("the target project is not active and approved")
        if approval is None:
            raise RecommendationError("an explicit user APPROVE_EXPLORATION decision is required")
        exploration = ExplorationRepository(self.database_url).create(
            current.riff_id,
            actor="user",
            target_project_id=current.project_id,
        )
        with connection(self.database_url) as conn:
            conn.execute(
                "UPDATE project_recommendations SET status = 'ACCEPTED', updated_at = now() WHERE recommendation_id = %s",
                (recommendation_id,),
            )
        return {"recommendation": self.get(recommendation_id).to_dict(), "exploration": exploration.to_dict()}
