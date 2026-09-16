"""Thin, restart-safe conversational tool adapter over Riff's application layer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import re
from typing import Any, Mapping

from .decisions import DecisionError, DecisionRepository
from .db import connection
from .explorations import ExplorationError, ExplorationRepository
from .operations import PipelineError, PipelineRepository
from .prds import PrdError, ProjectRepository
from .riffs import RiffRepository
from .profile import ProfileRepository, ProfileValidationError
from .capabilities import CapabilityRepository, NormalizationError
from .recommendations import RecommendationError, RecommendationRepository
from .project_map import ProjectMapRepository
from .github_account import GitHubAccountError, GitHubAccountRepository
from .opportunities import OpportunityError, OpportunityRepository, build_execution_candidates, compare_candidates, extract_context, riff_candidate


USER_CONFIRMATION_TOKEN = "USER_CONFIRMED"

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "daily_riffs": {"description": "Read the persisted daily zero-to-three Riff result.", "required": ("run_date",)},
    "alternate_riffs": {"description": "Read other published Riffs related to the current result without repeating the rejected one.", "required": ("riff_id",)},
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
    "list_projects": {"description": "List bounded, approved GitHub project summaries.", "required": ()},
    "inspect_project": {"description": "Read one bounded GitHub project map and snapshot history.", "required": ("project_id",)},
    "match_riff_to_projects": {"description": "Match a Riff to existing projects with explainable dispositions.", "required": ("riff_id",)},
    "map_riff_to_scenario": {"description": "Map a Riff to one concrete user workflow or scenario without creating durable state.", "required": ("riff_id", "scenario")},
    "github_account_status": {"description": "Read the bounded status and scope of the user-authorized GitHub account observation.", "required": ()},
    "github_account_repositories": {"description": "List bounded repositories from the user-authorized GitHub account observation.", "required": ()},
    "github_account_onboard": {"description": "Onboard one explicitly selected GitHub account repository into the G26 project inventory after user confirmation.", "required": ("repository", "confirmation_token")},
    "propose_extension": {"description": "Accept an extension recommendation and create a targeted Exploration after explicit user confirmation.", "required": ("recommendation_id", "confirmation_token")},
    "override_recommendation": {"description": "Override a project recommendation with an explicit greenfield or defer choice.", "required": ("recommendation_id", "disposition", "reason", "confirmation_token")},
    "create_opportunity_context": {"description": "Extract and persist a bounded opportunity context plus execution candidates from structured input.", "required": ("source_url", "payload")},
    "inspect_opportunity": {"description": "Read a bounded opportunity context, evidence, constraints, and unknowns.", "required": ("opportunity_id",)},
    "list_execution_candidates": {"description": "List bounded execution candidates for an opportunity with project seams and risks.", "required": ("opportunity_id",)},
    "riff_execution_candidate": {"description": "Create one traceable candidate variant using a named bounded riff operation.", "required": ("opportunity_id", "candidate_id", "operation")},
    "compare_execution_candidates": {"description": "Compare bounded execution candidates on feasibility, distinctiveness, fit, learning, evidence, risk, and usefulness.", "required": ("opportunity_id",)},
    "select_execution_direction": {"description": "Record the user's selected execution direction without creating an Exploration or PRD.", "required": ("opportunity_id", "candidate_id", "reason", "confirmation_token")},
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
        except (AdapterError, DecisionError, ExplorationError, PrdError, PipelineError, ProfileValidationError, NormalizationError, RecommendationError, OpportunityError, GitHubAccountError, ValueError) as exc:
            raise AdapterError(str(exc)) from exc
        return {"tool": name, "result": result}

    def _daily_riffs(self, run_date: str) -> dict[str, Any]:
        requested = date.fromisoformat(run_date)
        repository = RiffRepository(self.database_url)
        result = repository.daily_result(requested)
        if result is None:
            latest = repository.latest_result(through=requested)
            latest_summary = None
            if latest is not None:
                latest_summary = {
                    "run_date": latest.to_dict()["run_date"],
                    "status": latest.to_dict()["status"],
                    "riffs": [
                        {
                            "reference": "the top Riff" if item.rank == 1 else f"Riff {item.rank}",
                            "rank": item.rank,
                            "underlying_capability": item.underlying_capability,
                            "hypothesis": item.hypothesis,
                            "recommendation": item.recommendation,
                            "associated_technologies": list(item.associated_technologies),
                            "evidence_quality": item.evidence_quality,
                            "epistemic_confidence": item.epistemic_confidence,
                        }
                        for item in latest.riffs
                    ],
                }
            return {
                "status": "NOT_FOUND",
                "requested_date": requested.isoformat(),
                "message": "No daily Riff was published for the requested date.",
                "latest_available": latest_summary,
                "next_action": "Run the daily pipeline for the requested date, or inspect the latest available result.",
            }
        return result.to_dict()

    def _resolve_riff_reference(self, reference: str) -> str:
        """Resolve a bounded natural Riff reference for MCP follow-ups."""
        value = str(reference).strip()
        if not value or (" " in value and value.lower() not in {"the top riff", "top riff", "the latest riff", "latest riff", "the current riff", "current riff"}):
            raise AdapterError("Riff reference is ambiguous or stale; use a named result from this conversation")
        with connection(self.database_url) as conn:
            exact = conn.execute("SELECT riff_id FROM riffs WHERE riff_id = %s", (value,)).fetchone()
            if exact is not None:
                return str(exact[0])
            if value.lower() in {"the top riff", "top riff", "the latest riff", "latest riff", "the current riff", "current riff"}:
                rows = conn.execute(
                    "SELECT r.riff_id FROM riffs r JOIN daily_riff_runs d ON d.daily_run_id = r.daily_run_id WHERE r.status = 'PUBLISHED' ORDER BY d.run_date DESC, d.created_at DESC, r.rank LIMIT 1"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT riff_id FROM riffs WHERE status = 'PUBLISHED' AND (underlying_capability ILIKE %s OR observation ILIKE %s) ORDER BY created_at DESC LIMIT 2",
                    (f"%{value}%", f"%{value}%"),
                ).fetchall()
        if not rows:
            raise AdapterError(f"no Riff matches '{value}'")
        if len(rows) > 1:
            raise AdapterError(f"Riff reference '{value}' matches multiple results; please disambiguate")
        return str(rows[0][0])

    def _alternate_riffs(self, riff_id: str, **kwargs: Any) -> dict[str, Any]:
        current_id = self._resolve_riff_reference(riff_id)
        with connection(self.database_url) as conn:
            rows = conn.execute(
                """SELECT r.rank, r.underlying_capability, r.hypothesis, r.recommendation,
                          r.confidence, r.evidence_quality, r.epistemic_confidence,
                          d.run_date
                   FROM riffs r JOIN daily_riff_runs d ON d.daily_run_id = r.daily_run_id
                   WHERE r.status = 'PUBLISHED' AND r.daily_run_id = (SELECT daily_run_id FROM riffs WHERE riff_id = %s)
                     AND r.riff_id <> %s ORDER BY r.rank LIMIT 5""",
                (current_id, current_id),
            ).fetchall()
        return {
            "status": "ALTERNATIVES",
            "excluded_reference": "the current Riff",
            "results": [
                {
                    "reference": f"Riff {row[0]}",
                    "rank": row[0],
                    "run_date": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
                    "underlying_capability": row[1],
                    "hypothesis": row[2],
                    "recommendation": row[3],
                    "confidence": float(row[4]),
                    "evidence_quality": float(row[5] or 0),
                    "epistemic_confidence": float(row[6] or 0),
                }
                for row in rows
            ],
            "next_action": "Choose an alternative by its capability or reference, then ask for evidence or scenario mapping.",
        }

    def _map_riff_to_scenario(self, riff_id: str, scenario: str, **kwargs: Any) -> dict[str, Any]:
        scenario_text = str(scenario).strip()
        if not scenario_text or len(scenario_text) > 1000:
            raise AdapterError("scenario must be a non-empty description under 1000 characters")
        investigation = DecisionRepository(self.database_url).investigation(self._resolve_riff_reference(riff_id))
        riff = dict(investigation.riff)
        capability = str(riff.get("underlying_capability", ""))
        corpus = " ".join(str(riff.get(key, "")) for key in ("observation", "hypothesis", "recommendation", "why_it_matters"))
        terms = {term for term in re.findall(r"[a-z0-9][a-z0-9-]{2,}", scenario_text.lower()) if term not in {"the", "and", "with", "for", "that", "from"}}
        matched = sorted(term for term in terms if term in corpus.lower() or term in capability.lower())
        fit = "DIRECT" if capability.lower() in scenario_text.lower() or len(matched) >= 2 else ("PARTIAL" if matched else "WEAK")
        return {
            "riff_reference": capability or "the current Riff",
            "scenario": scenario_text,
            "fit": fit,
            "matched_terms": matched[:10],
            "rationale": f"The scenario shares {len(matched)} bounded terms with the Riff's evidence-backed claim." if matched else "The scenario is not directly supported by the Riff wording; treat this as a hypothesis.",
            "evidence_quality": float(investigation.provenance_quality.get("evidence_quality", 0)),
            "uncertainty": investigation.provenance_quality.get("limitations", []),
            "next_action": "Use this mapping to refine the execution candidate; it does not create an Exploration or PRD.",
        }

    def _github_account_status(self, **kwargs: Any) -> dict[str, Any]:
        return GitHubAccountRepository(self.database_url).status()

    def _github_account_repositories(self, **kwargs: Any) -> dict[str, Any]:
        observation_id = kwargs.get("observation_id")
        limit = int(kwargs.get("limit", 50))
        observation = GitHubAccountRepository(self.database_url).get(observation_id) if observation_id else GitHubAccountRepository(self.database_url).current()
        return {"observation_id": observation.observation_id, "scope": observation.scope, "status": observation.status, "repositories": GitHubAccountRepository(self.database_url).repositories(observation.observation_id, limit=limit)}

    def _github_account_onboard(self, repository: str, confirmation_token: str, observation_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return GitHubAccountRepository(self.database_url).onboard_selection(observation_id, repository, selected_by=str(kwargs.get("selected_by", "user")), reason=kwargs.get("reason"))

    def _investigate_riff(self, riff_id: str) -> dict[str, Any]:
        investigation = DecisionRepository(self.database_url).investigation(self._resolve_riff_reference(riff_id))
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
        result = DecisionRepository(self.database_url).record_decision(self._resolve_riff_reference(riff_id), decision, reason, actor=str(kwargs.get("actor", "user")), actor_kind=str(kwargs.get("actor_kind", "USER")), structured_reason=kwargs.get("structured_reason"))
        return asdict(result)

    def _require_confirmation(self, token: str) -> None:
        if token != USER_CONFIRMATION_TOKEN:
            raise AdapterError("explicit user confirmation token is required")

    def _create_exploration(self, riff_id: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return ExplorationRepository(self.database_url).create(self._resolve_riff_reference(riff_id), actor="user").to_dict()

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

    def _list_projects(self, **kwargs: Any) -> dict[str, Any]:
        limit = int(kwargs.get("limit", 5))
        return {"projects": RecommendationRepository(self.database_url).list_projects(limit=limit)}

    def _inspect_project(self, project_id: str) -> dict[str, Any]:
        return ProjectMapRepository(self.database_url).inspect(project_id)

    def _match_riff_to_projects(self, riff_id: str, **kwargs: Any) -> dict[str, Any]:
        return RecommendationRepository(self.database_url).match_riff(self._resolve_riff_reference(riff_id), limit=int(kwargs.get("limit", 3)))

    def _propose_extension(self, recommendation_id: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return RecommendationRepository(self.database_url).accept_extension(recommendation_id)

    def _override_recommendation(self, recommendation_id: str, disposition: str, reason: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return RecommendationRepository(self.database_url).override(recommendation_id, disposition, reason).to_dict()

    def _create_opportunity_context(self, source_url: str, payload: Any, **kwargs: Any) -> dict[str, Any]:
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise AdapterError("payload must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise AdapterError("payload must be an object")
        context = extract_context(source_url, payload)
        repository = OpportunityRepository(self.database_url)
        repository.persist_context(context)
        candidates = repository.persist_candidates(build_execution_candidates(context, project_seam=kwargs.get("project_seam")))
        return {"context": context.to_dict(), "candidates": [item.to_dict() for item in candidates], "brief": _brief(context, candidates)}

    def _inspect_opportunity(self, opportunity_id: str, **kwargs: Any) -> dict[str, Any]:
        return OpportunityRepository(self.database_url).get_context(opportunity_id).to_dict()

    def _list_execution_candidates(self, opportunity_id: str, **kwargs: Any) -> dict[str, Any]:
        candidates = OpportunityRepository(self.database_url).list_candidates(opportunity_id, limit=int(kwargs.get("limit", 10)))
        return {"opportunity_id": opportunity_id, "candidates": [item.to_dict() for item in candidates]}

    def _riff_execution_candidate(self, candidate_id: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        repository = OpportunityRepository(self.database_url)
        opportunity_id = str(kwargs.get("opportunity_id", ""))
        if not opportunity_id:
            raise AdapterError("opportunity_id is required to riff a candidate")
        candidates = repository.list_candidates(opportunity_id, limit=10)
        candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise AdapterError("candidate not found")
        other_id = str(kwargs.get("other_candidate_id", ""))
        other = next((item for item in candidates if item.candidate_id == other_id), None) if other_id else None
        variant = riff_candidate(candidate, operation, other=other, constraint=kwargs.get("constraint"))
        repository.persist_candidates([variant])
        return variant.to_dict()

    def _compare_execution_candidates(self, opportunity_id: str, **kwargs: Any) -> dict[str, Any]:
        candidates = OpportunityRepository(self.database_url).list_candidates(opportunity_id, limit=int(kwargs.get("limit", 10)))
        return {"opportunity_id": opportunity_id, **compare_candidates(candidates)}

    def _select_execution_direction(self, opportunity_id: str, candidate_id: str, reason: str, confirmation_token: str, **kwargs: Any) -> dict[str, Any]:
        self._require_confirmation(confirmation_token)
        return OpportunityRepository(self.database_url).select(opportunity_id, candidate_id, reason)


def _brief(context: Any, candidates: list[Any]) -> dict[str, Any]:
    return {
        "title": context.title,
        "source_url": context.source_url,
        "constraints": {"platforms": list(context.platforms), "connectors": list(context.connectors), "permissions": list(context.permissions), "approvals": list(context.approvals), "security_boundaries": list(context.security_boundaries)},
        "unknowns": list(context.unknowns),
        "candidate_ids": [item.candidate_id for item in candidates],
        "next_approval": "APPROVE_EXPLORATION",
    }
