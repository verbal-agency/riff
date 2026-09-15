"""Thin, restart-safe conversational tool adapter over Riff's application layer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Mapping

from .decisions import DecisionError, DecisionRepository
from .db import connection
from .explorations import ExplorationError, ExplorationRepository
from .operations import PipelineError, PipelineRepository
from .prds import PrdError, ProjectRepository
from .riffs import RiffRepository
from .profile import ProfileRepository, ProfileValidationError
from .capabilities import CapabilityRepository, NormalizationError


USER_CONFIRMATION_TOKEN = "USER_CONFIRMED"

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "daily_riffs": {"description": "Read the persisted daily zero-to-three Riff result.", "required": ("run_date",)},
    "investigate_riff": {"description": "Inspect one Riff's score, calibrated provenance, evidence, counterevidence, gap, and provenance.", "required": ("riff_id",)},
    "search_riffs": {"description": "Search persisted Riffs by capability or text.", "required": ("query",)},
    "profile_lookup": {"description": "Read the public profile slice and gap classification for one capability.", "required": ("capability_id",)},
    "capability_lookup": {"description": "Read normalized capability and technology relationships.", "required": ("capability_id",)},
    "record_decision": {"description": "Persist a user decision and semantic reason.", "required": ("riff_id", "decision", "reason")},
    "create_exploration": {"description": "Create an Exploration after explicit user approval.", "required": ("riff_id", "confirmation_token")},
    "get_exploration": {"description": "Read one Exploration and its experiment options.", "required": ("exploration_id",)},
    "refine_exploration": {"description": "Reject and refine one experiment after user feedback.", "required": ("exploration_id", "experiment_id", "reason", "confirmation_token")},
    "select_experiment": {"description": "Select one Exploration experiment after user confirmation.", "required": ("exploration_id", "experiment_id", "confirmation_token")},
    "approve_prd": {"description": "Record the distinct user approval for PRD generation.", "required": ("exploration_id", "reason", "confirmation_token")},
    "generate_prd": {"description": "Generate the approved Exploration's persisted PRD and goals.", "required": ("exploration_id",)},
    "get_project": {"description": "Read a generated project PRD and goals.", "required": ("project_id",)},
    "export_project": {"description": "Export a generated project as stable Markdown.", "required": ("project_id",)},
    "operation_report": {"description": "Read a durable daily pipeline run report.", "required": ("run_id",)},
}


class AdapterError(ValueError):
    """A malformed tool call or an application-domain error."""


class RiffToolAdapter:
    """Dispatch typed tool calls without storing conversational state."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()]

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if name not in TOOL_SCHEMAS:
            raise AdapterError(f"unknown tool: {name}")
        args = dict(arguments or {})
        missing = [field for field in TOOL_SCHEMAS[name]["required"] if not str(args.get(field, "")).strip()]
        if missing:
            raise AdapterError(f"missing required tool arguments: {', '.join(missing)}")
        try:
            result = getattr(self, f"_{name}")(**args)
        except (AdapterError, DecisionError, ExplorationError, PrdError, PipelineError, ProfileValidationError, NormalizationError, ValueError) as exc:
            raise AdapterError(str(exc)) from exc
        return {"tool": name, "result": result}

    def _daily_riffs(self, run_date: str) -> dict[str, Any]:
        result = RiffRepository(self.database_url).daily_result(date.fromisoformat(run_date))
        if result is None:
            raise AdapterError("daily Riff result not found")
        return result.to_dict()

    def _investigate_riff(self, riff_id: str) -> dict[str, Any]:
        investigation = DecisionRepository(self.database_url).investigation(riff_id)
        riff = dict(investigation.riff)
        evidence = [self._evidence_item(item) for item in investigation.supporting_evidence]
        counter = [self._evidence_item(item) for item in investigation.counterevidence]
        companies = sorted({str(item.get("source_metadata", {}).get(key)) for item in evidence + counter for key in ("company", "company_name", "organization", "employer") if item.get("source_metadata", {}).get(key)})
        quality = investigation.provenance_quality
        return {"riff_id": investigation.riff_id, "status": investigation.status, "riff": riff, "score": riff.get("candidate_score", riff.get("confidence")), "evidence_quality": quality.get("evidence_quality", 0), "epistemic_confidence": quality.get("epistemic_confidence", 0), "confidence_policy_version": quality.get("policy_version"), "promotion": {"allowed": quality.get("promotion_allowed", False), "state": quality.get("state"), "limitations": quality.get("limitations", [])}, "strongest_evidence": evidence, "counterevidence": counter, "profile_gap": riff.get("user_relevance"), "sources": investigation.source_breakdown, "companies": companies, "provenance": {"supporting_receipt_ids": [item["receipt_id"] for item in evidence], "counter_receipt_ids": [item["receipt_id"] for item in counter], **quality}}

    def _search_riffs(self, query: str, **kwargs: Any) -> dict[str, Any]:
        needle = f"%{query.strip()}%"
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT riff_id, status, underlying_capability, hypothesis, recommendation FROM riffs WHERE observation ILIKE %s OR hypothesis ILIKE %s OR underlying_capability ILIKE %s ORDER BY created_at DESC LIMIT 20", (needle, needle, needle)).fetchall()
        return {"query": query.strip(), "results": [{"riff_id": str(row[0]), "status": str(row[1]), "underlying_capability": str(row[2]), "hypothesis": str(row[3]), "recommendation": str(row[4])} for row in rows]}

    def _profile_lookup(self, capability_id: str, **kwargs: Any) -> dict[str, Any]:
        view = ProfileRepository(self.database_url).view(capability_id, public=True)
        return {"capability_id": view.capability_id, "classification": view.assessment.classification if view.assessment else "UNKNOWN", "rationale": view.assessment.rationale if view.assessment else None, "public_evidence": [asdict(item) for item in view.evidence]}

    def _capability_lookup(self, capability_id: str, **kwargs: Any) -> dict[str, Any]:
        inspection = CapabilityRepository(self.database_url).inspect_capability(capability_id)
        if inspection is None:
            raise AdapterError("capability not found")
        return {"capability": asdict(inspection.capability), "concepts": inspection.concepts, "patterns": inspection.patterns, "technologies": [asdict(item) for item in inspection.technologies]}

    @staticmethod
    def _evidence_item(item: Mapping[str, Any]) -> dict[str, Any]:
        raw = item.get("raw_content")
        bounded = raw[:4000] if isinstance(raw, str) else raw
        result = {"receipt_id": item.get("receipt_id"), "evidence_id": item.get("evidence_id"), "summary": item.get("summary"), "title": item.get("title"), "canonical_url": item.get("canonical_url"), "raw_content": bounded, "source_metadata": item.get("source_metadata", {})}
        if isinstance(raw, str) and len(raw) > 4000:
            result["raw_content_truncated"] = True
        return result

    def _record_decision(self, riff_id: str, decision: str, reason: str, **kwargs: Any) -> dict[str, Any]:
        result = DecisionRepository(self.database_url).record_decision(riff_id, decision, reason, actor=str(kwargs.get("actor", "user")), actor_kind=str(kwargs.get("actor_kind", "USER")), structured_reason=kwargs.get("structured_reason"))
        return asdict(result)

    def _require_confirmation(self, token: str) -> None:
        if token != USER_CONFIRMATION_TOKEN:
            raise AdapterError("explicit user confirmation token is required")

    def _create_exploration(self, riff_id: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return ExplorationRepository(self.database_url).create(riff_id, actor="user").to_dict()

    def _get_exploration(self, exploration_id: str) -> dict[str, Any]:
        return ExplorationRepository(self.database_url).get(exploration_id).to_dict()

    def _refine_exploration(self, exploration_id: str, experiment_id: str, reason: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return ExplorationRepository(self.database_url).refine(exploration_id, experiment_id, reason, actor="user").to_dict()

    def _select_experiment(self, exploration_id: str, experiment_id: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return ExplorationRepository(self.database_url).select_experiment(exploration_id, experiment_id, actor="user").to_dict()

    def _approve_prd(self, exploration_id: str, reason: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        approval_id = ProjectRepository(self.database_url).approve_prd(exploration_id, reason, actor="user")
        return {"approval_id": approval_id, "exploration_id": exploration_id, "status": "APPROVED"}

    def _generate_prd(self, exploration_id: str, **kwargs: Any) -> dict[str, Any]:
        return ProjectRepository(self.database_url).generate(exploration_id, actor="adapter").to_dict()

    def _get_project(self, project_id: str) -> dict[str, Any]:
        return ProjectRepository(self.database_url).get(project_id).to_dict()

    def _export_project(self, project_id: str) -> dict[str, Any]:
        return {"project_id": project_id, "markdown": ProjectRepository(self.database_url).export_markdown(project_id)}

    def _operation_report(self, run_id: str) -> dict[str, Any]:
        return PipelineRepository(self.database_url).report(run_id)
