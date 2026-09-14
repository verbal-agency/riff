"""Bounded, structured daily Riff generation and publication.

The reasoning provider is intentionally replaceable.  This module owns the
deterministic parts of the contract: bounded context, validation, citation
eligibility, publication gating, persistence, and idempotent daily runs.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from psycopg.types.json import Jsonb

from .db import connection


RIFF_STATUSES = {"DRAFT", "PUBLISHED", "REJECTED", "SKIPPED"}
CLAIM_TYPES = {"OBSERVATION", "HYPOTHESIS", "RECOMMENDATION", "COUNTEREVIDENCE"}
REQUIRED_TEXT_FIELDS = (
    "observation", "hypothesis", "why_now", "why_it_matters", "user_relevance",
    "underlying_capability", "recommendation", "strongest_counterargument",
    "alternative_explanation",
)


class RiffValidationError(ValueError):
    """A provider result or publication request violates the Riff contract."""


class ReasoningProvider(Protocol):
    version: str

    def generate(self, context: "RiffContext") -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class CandidateContext:
    candidate_id: str
    capability_id: str
    score: float
    classification: str
    observation: str
    receipt_ids: tuple[str, ...]
    profile_slice: tuple[dict[str, Any], ...] = ()
    decision_ids: tuple[str, ...] = ()
    profile_state: str = "UNKNOWN"
    associated_technologies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RiffContext:
    candidate_id: str
    capability_id: str
    score: float
    classification: str
    observation: str
    receipt_ids: tuple[str, ...]
    receipt_summaries: tuple[dict[str, Any], ...]
    profile_slice: tuple[dict[str, Any], ...]
    decision_ids: tuple[str, ...]
    profile_state: str
    associated_technologies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiffDraft:
    observation: str
    hypothesis: str
    why_now: str
    why_it_matters: str
    user_relevance: str
    underlying_capability: str
    recommendation: str
    confidence: float
    strongest_counterargument: str
    alternative_explanation: str
    falsification_conditions: tuple[str, ...]
    associated_technologies: tuple[str, ...]
    supporting_receipt_ids: tuple[str, ...]
    counter_receipt_ids: tuple[str, ...]
    citations: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PublishedRiff:
    riff_id: str
    daily_run_id: str
    rank: int
    status: str
    observation: str
    hypothesis: str
    why_now: str
    why_it_matters: str
    user_relevance: str
    underlying_capability: str
    recommendation: str
    confidence: float
    strongest_counterargument: str
    alternative_explanation: str
    falsification_conditions: tuple[str, ...]
    associated_technologies: tuple[str, ...]
    supporting_receipt_ids: tuple[str, ...]
    counter_receipt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DailyResult:
    daily_run_id: str
    run_date: date
    generation_policy_version: str
    input_fingerprint: str
    status: str
    empty_reason: str | None
    riffs: tuple[PublishedRiff, ...]
    provider_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["run_date"] = self.run_date.isoformat()
        value["riffs"] = [asdict(item) for item in self.riffs]
        return value


class RiffRepository:
    """Persistence for daily runs, bounded contexts, Riffs, and citations."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def eligible_receipts(self, receipt_ids: Sequence[str]) -> set[str]:
        if not receipt_ids:
            return set()
        with connection(self.database_url) as conn:
            rows = conn.execute(
                """SELECT r.receipt_id
                   FROM evidence_receipts r
                   JOIN evidence_versions e ON e.evidence_id = r.evidence_id
                   WHERE r.receipt_id = ANY(%s) AND r.status = 'SUCCEEDED'
                     AND e.raw_content IS NOT NULL""",
                (list(receipt_ids),),
            ).fetchall()
        return {_text(row[0]) for row in rows}

    def existing_run(self, input_fingerprint: str) -> DailyResult | None:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT daily_run_id, run_date, generation_policy_version, input_fingerprint, status, empty_reason FROM daily_riff_runs WHERE input_fingerprint = %s",
                (input_fingerprint,),
            ).fetchone()
            if row is None:
                return None
            riffs = conn.execute(
                """SELECT riff_id, daily_run_id, rank, status, observation, hypothesis, why_now,
                          why_it_matters, user_relevance, underlying_capability, recommendation,
                          confidence, strongest_counterargument, alternative_explanation,
                          falsification_conditions, associated_technologies,
                          supporting_receipt_ids, counter_receipt_ids
                   FROM riffs WHERE daily_run_id = %s AND status = 'PUBLISHED' ORDER BY rank""",
                (row[0],),
            ).fetchall()
        return _daily_result(row, riffs)

    def daily_result(self, run_date: date) -> DailyResult | None:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT daily_run_id, run_date, generation_policy_version, input_fingerprint, status, empty_reason FROM daily_riff_runs WHERE run_date = %s ORDER BY created_at DESC LIMIT 1",
                (run_date,),
            ).fetchone()
            if row is None:
                return None
            riffs = conn.execute(
                """SELECT riff_id, daily_run_id, rank, status, observation, hypothesis, why_now,
                          why_it_matters, user_relevance, underlying_capability, recommendation,
                          confidence, strongest_counterargument, alternative_explanation,
                          falsification_conditions, associated_technologies,
                          supporting_receipt_ids, counter_receipt_ids
                   FROM riffs WHERE daily_run_id = %s AND status = 'PUBLISHED' ORDER BY rank""",
                (row[0],),
            ).fetchall()
        return _daily_result(row, riffs)

    def save_run(self, result: DailyResult, contexts: Sequence[RiffContext], drafts: Sequence[tuple[int, RiffDraft, str]], *, rejected: int = 0) -> DailyResult:
        with connection(self.database_url) as conn:
            conn.execute(
                """INSERT INTO daily_riff_runs (daily_run_id, run_date, generation_policy_version, input_fingerprint, status, empty_reason)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (input_fingerprint) DO NOTHING""",
                (result.daily_run_id, result.run_date, result.generation_policy_version, result.input_fingerprint, result.status, result.empty_reason),
            )
            existing = conn.execute("SELECT daily_run_id FROM daily_riff_runs WHERE input_fingerprint = %s", (result.input_fingerprint,)).fetchone()
            run_id = _text(existing[0]) if existing else result.daily_run_id
            for context in contexts:
                conn.execute(
                    """INSERT INTO riff_contexts (context_id, daily_run_id, candidate_id, receipt_ids, profile_slice, decision_ids)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (daily_run_id, candidate_id) DO NOTHING""",
                    (str(uuid.uuid4()), run_id, context.candidate_id, Jsonb(list(context.receipt_ids)), Jsonb(list(context.profile_slice)), Jsonb(list(context.decision_ids))),
                )
            for rank, draft, status in drafts:
                riff_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{rank}"))
                conn.execute(
                    """INSERT INTO riffs (riff_id, daily_run_id, rank, status, observation, hypothesis, why_now,
                       why_it_matters, user_relevance, underlying_capability, recommendation, confidence,
                       strongest_counterargument, alternative_explanation, falsification_conditions,
                       associated_technologies, supporting_receipt_ids, counter_receipt_ids)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (daily_run_id, rank) DO NOTHING""",
                    (riff_id, run_id, rank, status, draft.observation, draft.hypothesis, draft.why_now, draft.why_it_matters, draft.user_relevance, draft.underlying_capability, draft.recommendation, draft.confidence, draft.strongest_counterargument, draft.alternative_explanation, Jsonb(list(draft.falsification_conditions)), Jsonb(list(draft.associated_technologies)), Jsonb(list(draft.supporting_receipt_ids)), Jsonb(list(draft.counter_receipt_ids))),
                )
                if status == "PUBLISHED":
                    for citation in draft.citations:
                        conn.execute(
                            "INSERT INTO riff_citations (citation_id, riff_id, receipt_id, claim_type, statement) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            (str(uuid.uuid4()), riff_id, citation["receipt_id"], citation["claim_type"], citation["statement"]),
                        )
        return self.existing_run(result.input_fingerprint) or result


class RiffContextAssembler:
    def __init__(self, repository: RiffRepository, *, max_receipts: int = 5, max_profile_items: int = 10, max_decisions: int = 10):
        self.repository = repository
        self.max_receipts = max_receipts
        self.max_profile_items = max_profile_items
        self.max_decisions = max_decisions

    def assemble(self, candidate: CandidateContext) -> RiffContext:
        receipt_ids = tuple(candidate.receipt_ids[: self.max_receipts])
        eligible = self.repository.eligible_receipts(receipt_ids)
        if set(receipt_ids) != eligible:
            raise RiffValidationError("candidate context contains an unknown or ineligible receipt")
        with connection(self.repository.database_url) as conn:
            rows = conn.execute(
                "SELECT receipt_id, summary, source_metadata, uncertainty FROM evidence_receipts WHERE receipt_id = ANY(%s) AND status = 'SUCCEEDED' ORDER BY receipt_id",
                (list(receipt_ids),),
            ).fetchall()
        summaries = tuple({"receipt_id": _text(row[0]), "summary": _text(row[1]), "source_metadata": _json(row[2]), "uncertainty": _json(row[3])} for row in rows)
        return RiffContext(candidate.candidate_id, candidate.capability_id, candidate.score, candidate.classification, candidate.observation, receipt_ids, summaries, tuple(candidate.profile_slice[: self.max_profile_items]), tuple(candidate.decision_ids[: self.max_decisions]), candidate.profile_state, tuple(candidate.associated_technologies))


class DeterministicReasoningProvider:
    """Offline provider used for golden tests and local smoke runs."""

    version = "deterministic-riff-v1"

    def generate(self, context: RiffContext) -> Mapping[str, Any]:
        gap = context.profile_state
        if gap == "SIGNALING_GAP":
            intervention = "Build and publish a small artifact that demonstrates this capability in public."
        elif gap == "IMPLEMENTATION_GAP":
            intervention = "Prototype the capability in a focused, working implementation and record the result."
        elif gap == "KNOWLEDGE_GAP":
            intervention = "Study the underlying concept, then validate it with a small hands-on exercise."
        else:
            intervention = "Compare the evidence with your current work and run a bounded experiment before adopting it."
        summary = context.receipt_summaries[0]["summary"] if context.receipt_summaries else context.observation
        return {"observation": context.observation, "hypothesis": f"This may indicate a durable change around {context.capability_id}.", "why_now": "Recent independent evidence makes this worth reviewing now.", "why_it_matters": f"It could affect decisions involving {context.capability_id}.", "user_relevance": f"The current profile state is {gap}; the intervention should match that gap.", "underlying_capability": context.capability_id, "recommendation": intervention, "confidence": min(0.95, max(0.55, context.score)), "strongest_counterargument": "The evidence may reflect temporary attention or vendor-specific promotion rather than durable demand.", "alternative_explanation": "A short-lived release cycle could explain the observed concentration.", "falsification_conditions": ["Independent sources stop reporting the capability over the next review window.", "A direct experiment fails to reproduce the claimed benefit."], "associated_technologies": list(context.associated_technologies), "supporting_receipt_ids": list(context.receipt_ids), "counter_receipt_ids": [], "citations": [{"receipt_id": receipt_id, "claim_type": "OBSERVATION", "statement": summary} for receipt_id in context.receipt_ids]}


def validate_draft(output: Mapping[str, Any], context: RiffContext, eligible_receipt_ids: set[str]) -> RiffDraft:
    if not isinstance(output, Mapping):
        raise RiffValidationError("provider output must be an object")
    missing = [name for name in REQUIRED_TEXT_FIELDS if not isinstance(output.get(name), str) or not output[name].strip()]
    if missing:
        raise RiffValidationError(f"missing required fields: {', '.join(missing)}")
    confidence = output.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise RiffValidationError("confidence must be between 0 and 1")
    falsification = _strings(output.get("falsification_conditions"), "falsification_conditions")
    if len(output["strongest_counterargument"].strip()) < 20 or len(output["alternative_explanation"].strip()) < 20:
        raise RiffValidationError("counterargument and alternative explanation are too weak")
    supporting = _strings(output.get("supporting_receipt_ids", []), "supporting_receipt_ids")
    counter = _strings(output.get("counter_receipt_ids", []), "counter_receipt_ids")
    if not supporting or not set(supporting).issubset(set(context.receipt_ids) & eligible_receipt_ids):
        raise RiffValidationError("supporting citations must resolve to eligible context receipts")
    if set(counter) - (set(context.receipt_ids) & eligible_receipt_ids):
        raise RiffValidationError("counter citations must resolve to eligible context receipts")
    if len({output["observation"].strip(), output["hypothesis"].strip(), output["recommendation"].strip()}) != 3:
        raise RiffValidationError("observation, hypothesis, and recommendation must be distinct")
    citations = []
    for item in output.get("citations", []):
        if not isinstance(item, Mapping) or item.get("receipt_id") not in (set(context.receipt_ids) & eligible_receipt_ids) or item.get("claim_type") not in CLAIM_TYPES or not str(item.get("statement", "")).strip():
            raise RiffValidationError("invalid citation")
        citations.append({"receipt_id": str(item["receipt_id"]), "claim_type": str(item["claim_type"]), "statement": str(item["statement"]).strip()})
    if not citations or not set(supporting).issubset({item["receipt_id"] for item in citations}):
        raise RiffValidationError("each supporting receipt must have a citation")
    return RiffDraft(*(str(output[name]).strip() for name in REQUIRED_TEXT_FIELDS[:7]), float(confidence), output["strongest_counterargument"].strip(), output["alternative_explanation"].strip(), tuple(falsification), tuple(_strings(output.get("associated_technologies", []), "associated_technologies")), tuple(supporting), tuple(counter), tuple(citations))


class DailyRiffService:
    def __init__(self, repository: RiffRepository, provider: ReasoningProvider, *, policy_version: str = "riff-policy-v1", max_candidates: int = 5, max_riffs: int = 3, quality_threshold: float = 0.5):
        if not 1 <= max_candidates <= 20 or not 1 <= max_riffs <= 3 or not 0 <= quality_threshold <= 1:
            raise RiffValidationError("invalid generation bounds")
        self.repository, self.provider, self.policy_version = repository, provider, policy_version
        self.max_candidates, self.max_riffs, self.quality_threshold = max_candidates, max_riffs, quality_threshold
        self.assembler = RiffContextAssembler(repository)

    def generate(self, run_date: date, candidates: Sequence[CandidateContext]) -> DailyResult:
        selected = sorted((item for item in candidates if item.score >= self.quality_threshold), key=lambda item: (-item.score, item.candidate_id))[: self.max_candidates]
        fingerprint = _fingerprint(run_date, self.policy_version, selected)
        cached = self.repository.existing_run(fingerprint)
        if cached:
            return cached
        contexts, drafts, rejected = [], [], 0
        for candidate in selected:
            try:
                context = self.assembler.assemble(candidate)
                contexts.append(context)
                draft = validate_draft(self.provider.generate(context), context, set(context.receipt_ids))
                if len(drafts) < self.max_riffs:
                    drafts.append((len(drafts) + 1, draft, "PUBLISHED"))
            except (RiffValidationError, RuntimeError):
                rejected += 1
        status = "COMPLETED" if drafts else "EMPTY"
        reason = None if drafts else ("No candidate met the quality threshold." if not selected else "No candidate produced a publication-ready, evidence-backed Riff.")
        result = DailyResult(str(uuid.uuid4()), run_date, self.policy_version, fingerprint, status, reason, tuple(_published_preview(result_id := "", result_run := "", rank, draft) for rank, draft, _ in drafts), provider_calls=len(selected))
        saved = self.repository.save_run(result, contexts, drafts, rejected=rejected)
        return saved


def _published_preview(_riff_id: str, _run_id: str, rank: int, draft: RiffDraft) -> PublishedRiff:
    return PublishedRiff("", "", rank, "PUBLISHED", draft.observation, draft.hypothesis, draft.why_now, draft.why_it_matters, draft.user_relevance, draft.underlying_capability, draft.recommendation, draft.confidence, draft.strongest_counterargument, draft.alternative_explanation, draft.falsification_conditions, draft.associated_technologies, draft.supporting_receipt_ids, draft.counter_receipt_ids)


def _fingerprint(run_date: date, policy: str, candidates: Sequence[CandidateContext]) -> str:
    payload = [{key: getattr(item, key) for key in ("candidate_id", "capability_id", "score", "classification", "observation", "receipt_ids", "profile_slice", "decision_ids", "profile_state", "associated_technologies")} for item in candidates]
    return hashlib.sha256(json.dumps({"date": run_date.isoformat(), "policy": policy, "candidates": payload}, sort_keys=True, default=str).encode()).hexdigest()


def _daily_result(row: tuple[Any, ...], riffs: Sequence[tuple[Any, ...]]) -> DailyResult:
    return DailyResult(_text(row[0]), row[1], _text(row[2]), _text(row[3]), _text(row[4]), _text(row[5]) if row[5] else None, tuple(_riff(row) for row in riffs))


def _riff(row: tuple[Any, ...]) -> PublishedRiff:
    values = [_json(value) if index >= 14 else value for index, value in enumerate(row)]
    return PublishedRiff(
        _text(values[0]), _text(values[1]), int(values[2]), _text(values[3]),
        _text(values[4]), _text(values[5]), _text(values[6]), _text(values[7]),
        _text(values[8]), _text(values[9]), _text(values[10]), float(values[11]),
        _text(values[12]), _text(values[13]), tuple(values[14]), tuple(values[15]),
        tuple(values[16]), tuple(values[17]),
    )


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RiffValidationError(f"{name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, str)):
        return json.loads(value.decode() if isinstance(value, bytes) else value)
    return value


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode()
    return value
