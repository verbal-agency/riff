"""Bounded opportunity context and execution-candidate riffing (G28)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

from .db import connection


PARSER_VERSION = "opportunity-context-v1"
POLICY_VERSION = "opportunity-riff-policy-v1"
OPERATIONS = {"COMBINE", "EXTEND", "NARROW", "INVERT", "TRANSFER", "CONSTRAIN"}
MAX_TEXT_CHARS = 20_000


class OpportunityError(ValueError):
    """Raised when an opportunity or candidate cannot be handled safely."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple)):
        raise OpportunityError("context fields must be lists or strings")
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, _hash(parts))}"


def _keyword_values(text: str, mapping: Mapping[str, Sequence[str]]) -> list[str]:
    lower = text.lower()
    return sorted({label for label, terms in mapping.items() if any(term.lower() in lower for term in terms)})


@dataclass(frozen=True, slots=True)
class OpportunityContext:
    opportunity_id: str
    source_url: str
    title: str
    version: int
    actors: tuple[str, ...]
    jobs_to_be_done: tuple[str, ...]
    workflow_stages: tuple[str, ...]
    data_surfaces: tuple[str, ...]
    tool_surfaces: tuple[str, ...]
    platforms: tuple[str, ...]
    connectors: tuple[str, ...]
    permissions: tuple[str, ...]
    approvals: tuple[str, ...]
    security_boundaries: tuple[str, ...]
    success_measures: tuple[str, ...]
    unknowns: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    extraction_confidence: float
    parser_version: str = PARSER_VERSION
    policy_version: str = POLICY_VERSION
    input_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "actors", "jobs_to_be_done", "workflow_stages", "data_surfaces", "tool_surfaces",
            "platforms", "connectors", "permissions", "approvals", "security_boundaries",
            "success_measures", "unknowns", "evidence",
        ):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True, slots=True)
class ExecutionCandidate:
    candidate_id: str
    opportunity_id: str
    parent_candidate_id: str | None
    operation: str
    thesis: str
    target_user: str
    problem: str
    required_capabilities: tuple[str, ...]
    platform_role: str
    project_seam: str | None
    boundary: str
    deliverables: tuple[str, ...]
    evaluation_measures: tuple[str, ...]
    risks: tuple[str, ...]
    evidence_of_competence: tuple[str, ...]
    scores: dict[str, float]
    rationale: str
    assumptions: tuple[str, ...]
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("required_capabilities", "deliverables", "evaluation_measures", "risks", "evidence_of_competence", "assumptions"):
            value[key] = list(value[key])
        return value


def extract_context(source_url: str, payload: Mapping[str, Any], *, version: int = 1) -> OpportunityContext:
    """Extract a bounded context from structured fixture fields and text."""

    source_url = _text(source_url) or _text(payload.get("source_url"))
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.netloc or parsed_url.username or parsed_url.password:
        raise OpportunityError("opportunity source_url must be an HTTP(S) URL")
    title = _text(payload.get("title")) or _text(payload.get("name")) or "Untitled opportunity"
    text = " ".join(_text(payload.get(key)) for key in ("description", "text", "body", "summary"))
    if len(text) > MAX_TEXT_CHARS:
        raise OpportunityError("opportunity text exceeds the configured bound")
    def field(name: str, default: Sequence[str] = ()) -> list[str]:
        return _list(payload.get(name)) or list(default)

    platforms = field("platforms")
    if re.search(r"\bperplexity computer\b", text, re.I) and "Perplexity Computer" not in platforms:
        platforms.append("Perplexity Computer")
    platforms.extend(_keyword_values(text, {"ChatGPT": ("chatgpt",), "MCP": ("model context protocol", " mcp "), "Temporal": ("temporal",), "LangGraph": ("langgraph",)}))
    connectors = field("connectors") or _keyword_values(text, {"API": (" api", "api "), "MCP connector": ("mcp", "connector"), "Browser automation": ("browser", "computer use")})
    permissions = field("permissions") or _keyword_values(text, {"OAuth/access scope": ("oauth", "permission", "access scope", "credentials"), "Private data boundary": ("private data", "sensitive data")})
    approvals = field("approvals") or _keyword_values(text, {"Human approval": ("human approval", "approval", "review")})
    security = field("security_boundaries") or _keyword_values(text, {"Least privilege": ("least privilege", "scopes"), "Prompt/tool injection": ("prompt injection", "tool injection"), "Auditability": ("audit", "auditability", "trace")})
    tools = field("tool_surfaces") or _keyword_values(text, {"Browser": ("browser", "web"), "API tools": ("api", "tool call", "connector"), "GitHub": ("github", "repository")})
    stages = field("workflow_stages") or ["intake", "plan", "execute", "verify"]
    actors = field("actors") or ["operator", "agent"]
    jobs = field("jobs_to_be_done") or ["complete a consequential multi-step workflow"]
    data = field("data_surfaces") or ["opportunity requirements", "workflow state", "tool results"]
    measures = field("success_measures") or ["task completion", "recovery after interruption", "auditable result"]
    unknowns = field("unknowns") or ["provider-specific limits", "production workload shape"]
    evidence = payload.get("evidence", [{"source_url": source_url, "kind": "opportunity", "confidence": 0.8}])
    if not isinstance(evidence, list):
        raise OpportunityError("opportunity evidence must be a list")
    context_payload = {
        "source_url": source_url, "title": title, "actors": actors, "jobs_to_be_done": jobs,
        "workflow_stages": stages, "data_surfaces": data, "tool_surfaces": tools, "platforms": sorted(set(platforms)),
        "connectors": connectors, "permissions": permissions, "approvals": approvals, "security_boundaries": security,
        "success_measures": measures, "unknowns": unknowns, "evidence": evidence,
    }
    input_hash = _hash(context_payload)
    opportunity_id = _id("opp", source_url, input_hash)
    return OpportunityContext(
        opportunity_id, source_url, title, version,
        tuple(actors), tuple(jobs), tuple(stages), tuple(data), tuple(tools), tuple(sorted(set(platforms))),
        tuple(connectors), tuple(permissions), tuple(approvals), tuple(security), tuple(measures), tuple(unknowns),
        tuple(dict(item) for item in evidence if isinstance(item, Mapping)),
        0.8 if evidence and all(isinstance(item, Mapping) for item in evidence) else 0.45,
        input_hash=input_hash,
    )


def build_execution_candidates(context: OpportunityContext, *, project_seam: str | None = None) -> list[ExecutionCandidate]:
    """Create three materially different, bounded candidates."""

    capability = "durable workflow execution" if any("recover" in item.lower() or "workflow" in item.lower() for item in context.success_measures + context.jobs_to_be_done) else "opportunity-aware agent execution"
    platform_role = ", ".join(context.platforms) if context.platforms else "provider-neutral tools"
    seam = _text(project_seam) or None
    specs = [
        ("Build a public artifact that proves the workflow can resume safely.", "operator", "make interruption and recovery observable", seam, "existing-project extension" if seam else "greenfield artifact", ("replayable workflow demo", "architecture note"), ("resume success rate", "replay determinism"), ("scope creep",), ("durable execution", "observability"), "A concrete seam makes existing-project leverage worthwhile." if seam else "No project seam was supplied, so this remains a bounded greenfield artifact."),
        ("Compare two execution approaches under identical failures.", "engineer", "measure trade-offs rather than assume one runtime wins", None, "standalone comparative benchmark", ("two implementations", "comparison table"), ("recovery latency", "failure coverage"), ("benchmark bias",), ("workflow testing", "measurement"), "A controlled comparison preserves a credible greenfield alternative."),
        ("Probe the failure boundary and publish the guardrail.", "operator", "show where automation must stop for approval or security", None, "failure-mode probe", ("failure fixture", "guardrail decision"), ("unsafe-action prevention", "diagnostic completeness"), ("false confidence",), ("security boundaries", "human approval"), "A failure-first slice can expose unknowns before production scope."),
    ]
    result: list[ExecutionCandidate] = []
    for index, (thesis, target, problem, candidate_seam, boundary, deliverables, measures, risks, required, rationale) in enumerate(specs, 1):
        payload = {"index": index, "thesis": thesis, "seam": candidate_seam, "boundary": boundary, "required": required}
        result.append(ExecutionCandidate(
            _id("cand", context.opportunity_id, index), context.opportunity_id, None, "GENERATE", thesis, target,
            problem, tuple(required), platform_role, candidate_seam, boundary, tuple(deliverables), tuple(measures),
            tuple(risks), tuple([f"publish {item}" for item in deliverables]),
            {"feasibility": 0.75 - index * 0.03, "distinctiveness": 0.62 + index * 0.06, "personal_fit": 0.7, "learning_value": 0.8, "evidence_value": 0.82, "scope_risk": 0.25 + index * 0.08, "customer_usefulness": 0.7},
            rationale, tuple(context.unknowns), _hash(payload),
        ))
    return result


def riff_candidate(candidate: ExecutionCandidate, operation: str, *, other: ExecutionCandidate | None = None, constraint: str | None = None) -> ExecutionCandidate:
    operation = _text(operation).upper()
    if operation not in OPERATIONS:
        raise OpportunityError(f"unsupported riff operation: {operation}")
    thesis = candidate.thesis
    boundary = candidate.boundary
    seam = candidate.project_seam
    deliverables = list(candidate.deliverables)
    assumptions = list(candidate.assumptions)
    if operation == "COMBINE":
        if other is None:
            raise OpportunityError("COMBINE requires another candidate")
        thesis = f"{candidate.thesis.rstrip('.')} while measuring {other.problem}."
        deliverables = list(dict.fromkeys(deliverables + list(other.deliverables)))[:4]
        assumptions.append(f"combined with {other.candidate_id}")
    elif operation == "EXTEND":
        thesis = f"{candidate.thesis.rstrip('.')} Extend the slice to a second recovery boundary."
        deliverables.append("second interruption boundary")
    elif operation == "NARROW":
        thesis = f"{candidate.thesis.rstrip('.')} Limit the demo to one representative workflow."
        deliverables = deliverables[:1] + (deliverables[1:2] if len(deliverables) > 1 else [])
        boundary = f"{boundary}; one workflow only"
    elif operation == "INVERT":
        thesis = f"{candidate.thesis.rstrip('.')} Start from the failure and derive the minimum safe automation."
        boundary = "failure-first guardrail"
    elif operation == "TRANSFER":
        thesis = f"{candidate.thesis.rstrip('.')} Transfer the pattern to a second tool surface."
        deliverables.append("cross-surface replay note")
    elif operation == "CONSTRAIN":
        constraint = _text(constraint) or "no private data and one-hour replay budget"
        thesis = f"{candidate.thesis.rstrip('.')} Under constraint: {constraint}."
        assumptions.append(constraint)
        boundary = f"{boundary}; {constraint}"
    payload = {"parent": candidate.candidate_id, "operation": operation, "thesis": thesis, "boundary": boundary, "deliverables": deliverables, "assumptions": assumptions, "other": other.candidate_id if other else None}
    return ExecutionCandidate(
        _id("cand", candidate.opportunity_id, candidate.candidate_id, operation, payload), candidate.opportunity_id,
        candidate.candidate_id, operation, thesis, candidate.target_user, candidate.problem, candidate.required_capabilities,
        candidate.platform_role, seam, boundary, tuple(deliverables[:4]), candidate.evaluation_measures,
        candidate.risks, candidate.evidence_of_competence, dict(candidate.scores),
        f"{operation} preserves lineage from {candidate.candidate_id} and makes the changed assumption explicit.",
        tuple(assumptions), _hash(payload),
    )


def compare_candidates(candidates: Sequence[ExecutionCandidate]) -> dict[str, Any]:
    if not candidates:
        raise OpportunityError("at least one candidate is required")
    rows = []
    for candidate in candidates[:5]:
        scores = candidate.scores
        weighted = round(sum(scores.get(key, 0.0) * weight for key, weight in (("feasibility", .2), ("distinctiveness", .2), ("personal_fit", .15), ("learning_value", .2), ("evidence_value", .15), ("customer_usefulness", .1))) - scores.get("scope_risk", 0) * .15, 4)
        rows.append({"candidate_id": candidate.candidate_id, "operation": candidate.operation, "thesis": candidate.thesis, "scores": scores, "weighted_score": weighted, "project_seam": candidate.project_seam, "lineage": candidate.parent_candidate_id})
    return {"candidates": sorted(rows, key=lambda item: (-item["weighted_score"], item["candidate_id"])), "policy_version": POLICY_VERSION}


class OpportunityRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def persist_context(self, context: OpportunityContext) -> OpportunityContext:
        with connection(self.database_url) as conn:
            prior = conn.execute("SELECT COALESCE(MAX(version), 0) FROM opportunities WHERE source_url = %s", (context.source_url,)).fetchone()[0]
            version = max(context.version, int(prior or 0))
            conn.execute(
                "INSERT INTO opportunities (opportunity_id, source_url, title, version, input_hash, parser_version, policy_version, context, evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (opportunity_id) DO NOTHING",
                (context.opportunity_id, context.source_url, context.title, version, context.input_hash, context.parser_version, context.policy_version, Jsonb(context.to_dict()), Jsonb(list(context.evidence))),
            )
        return self.get_context(context.opportunity_id)

    def get_context(self, opportunity_id: str) -> OpportunityContext:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT context FROM opportunities WHERE opportunity_id = %s", (opportunity_id,)).fetchone()
        if row is None:
            raise OpportunityError("opportunity not found")
        data = row[0]
        return OpportunityContext(
            _text(data["opportunity_id"]), _text(data["source_url"]), _text(data["title"]), int(data["version"]),
            *(tuple(data.get(key, [])) for key in ("actors", "jobs_to_be_done", "workflow_stages", "data_surfaces", "tool_surfaces", "platforms", "connectors", "permissions", "approvals", "security_boundaries", "success_measures", "unknowns", "evidence")),
            float(data.get("extraction_confidence", 0.0)), _text(data.get("parser_version")) or PARSER_VERSION, _text(data.get("policy_version")) or POLICY_VERSION, _text(data.get("input_hash")),
        )

    def persist_candidates(self, candidates: Sequence[ExecutionCandidate]) -> list[ExecutionCandidate]:
        with connection(self.database_url) as conn:
            for candidate in candidates[:10]:
                conn.execute(
                    "INSERT INTO execution_candidates (candidate_id, opportunity_id, parent_candidate_id, operation, version, payload, input_hash) VALUES (%s,%s,%s,%s,1,%s,%s) ON CONFLICT (candidate_id) DO NOTHING",
                    (candidate.candidate_id, candidate.opportunity_id, candidate.parent_candidate_id, candidate.operation, Jsonb(candidate.to_dict()), candidate.input_hash),
                )
        return list(candidates[:10])

    def list_candidates(self, opportunity_id: str, limit: int = 10) -> list[ExecutionCandidate]:
        if not 1 <= limit <= 10:
            raise OpportunityError("candidate limit must be between 1 and 10")
        with connection(self.database_url) as conn:
            rows = conn.execute("SELECT payload FROM execution_candidates WHERE opportunity_id = %s ORDER BY created_at, candidate_id LIMIT %s", (opportunity_id, limit)).fetchall()
        return [_candidate_from_dict(row[0]) for row in rows]

    def select(self, opportunity_id: str, candidate_id: str, reason: str) -> dict[str, Any]:
        if not _text(reason):
            raise OpportunityError("selection reason is required")
        with connection(self.database_url) as conn:
            exists = conn.execute("SELECT 1 FROM execution_candidates WHERE opportunity_id = %s AND candidate_id = %s", (opportunity_id, candidate_id)).fetchone()
            if exists is None:
                raise OpportunityError("candidate does not belong to opportunity")
            conn.execute("INSERT INTO opportunity_selections (opportunity_id, candidate_id, reason) VALUES (%s,%s,%s) ON CONFLICT (opportunity_id) DO UPDATE SET candidate_id=EXCLUDED.candidate_id, reason=EXCLUDED.reason, selected_at=now()", (opportunity_id, candidate_id, reason))
        return {"opportunity_id": opportunity_id, "candidate_id": candidate_id, "reason": reason, "status": "SELECTED", "next_approval": "APPROVE_EXPLORATION"}


def _candidate_from_dict(data: Mapping[str, Any]) -> ExecutionCandidate:
    lists = {key: tuple(data.get(key, [])) for key in ("required_capabilities", "deliverables", "evaluation_measures", "risks", "evidence_of_competence", "assumptions")}
    return ExecutionCandidate(
        _text(data.get("candidate_id")), _text(data.get("opportunity_id")), data.get("parent_candidate_id"), _text(data.get("operation")),
        _text(data.get("thesis")), _text(data.get("target_user")), _text(data.get("problem")), lists["required_capabilities"],
        _text(data.get("platform_role")), data.get("project_seam"), _text(data.get("boundary")), lists["deliverables"],
        lists["evaluation_measures"], lists["risks"], lists["evidence_of_competence"], dict(data.get("scores", {})),
        _text(data.get("rationale")), lists["assumptions"], _text(data.get("input_hash")),
    )
