"""Live source composition for the scheduled daily worker (G40).

This module deliberately composes the existing source runners instead of
reimplementing their parsers or persistence contracts.  It also keeps the
live boundary explicit: fixture/test/quarantined rows are never selected for a
live daily result.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .capabilities import CapabilityRepository, DeterministicNormalizer, NormalizationService
from .evidence import SourceType
from .evidence_repository import EvidenceRepository
from .github_ingestion import GitHubIngestionRunner, HttpGitHubFetcher
from .ingestion import HttpFeedFetcher
from .ingestion_repository import CollectionSummary, IngestionRepository, RunStatus
from .job_collection import JobCollectionRunner
from .job_fetch import HttpJobFetcher
from .job_source_policy import JobPolicyError, JobSourcePolicy, load_policy
from .operations import PipelineError, PipelineRepository, STAGES
from .profile import ProfileRepository
from .receipts import LiveHeuristicExtractor, ReceiptProcessor, ReceiptRepository
from .riffs import CandidateContext, DailyRiffService, DeterministicReasoningProvider, RiffRepository
from .signals import SignalObservation, SignalRanker, SignalRepository


class LiveWorkerError(RuntimeError):
    """Live worker configuration or composition failed."""


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    source_type: str
    status: str
    source_ids: tuple[str, ...] = ()
    run_id: str | None = None
    stored: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed_transient: int = 0
    failed_permanent: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"source_ids": list(self.source_ids)}


@dataclass(frozen=True, slots=True)
class LiveCollectionResult:
    outcomes: tuple[SourceOutcome, ...]
    evidence_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    started_at: datetime

    @property
    def attempted_count(self) -> int:
        return sum(len(item.source_ids) for item in self.outcomes if item.status not in {"SKIPPED"})

    @property
    def failure_count(self) -> int:
        return sum(item.failed_transient + item.failed_permanent + (1 if item.status == "FAILED" else 0) for item in self.outcomes)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status in {"SUCCEEDED", "PARTIAL"})


class LiveSourceCollector:
    """Run enabled, database-configured source runners once."""

    def __init__(
        self,
        database_url: str,
        *,
        job_policy_path: str | Path = "config/job_sources.json",
        source_ids: list[str] | None = None,
        job_source_id: str | None = None,
        feed_fetcher=None,
        github_fetcher=None,
        job_fetcher=None,
    ):
        self.database_url = database_url
        self.job_policy_path = job_policy_path
        self.source_ids = set(source_ids or [])
        self.job_source_id = job_source_id
        self.feed_fetcher = feed_fetcher or HttpFeedFetcher()
        self.github_fetcher = github_fetcher or HttpGitHubFetcher(token=os.environ.get("GITHUB_TOKEN"))
        self.job_fetcher = job_fetcher or HttpJobFetcher()

    def collect(self, heartbeat: Callable[[], bool] | None = None) -> LiveCollectionResult:
        started_at = datetime.now(timezone.utc)
        ingestion = IngestionRepository(self.database_url)
        evidence = EvidenceRepository(self.database_url)
        configured = ingestion.list_sources(source_ids=sorted(self.source_ids) if self.source_ids else None)
        outcomes: list[SourceOutcome] = []
        tracked_source_ids = tuple(item.source_id for item in configured if item.enabled)

        writing = tuple(item for item in configured if item.source_type == SourceType.TECHNICAL_WRITING and item.enabled)
        if writing:
            if heartbeat:
                heartbeat()
            outcomes.append(self._writing(ingestion, evidence, [item.source_id for item in writing]))
        else:
            outcomes.append(SourceOutcome("TECHNICAL_WRITING", "SKIPPED", reason="NO_ENABLED_APPROVED_SOURCES"))

        github = tuple(item for item in configured if item.source_type == SourceType.GITHUB and item.enabled)
        if github:
            if heartbeat:
                heartbeat()
            outcomes.append(self._github(ingestion, evidence, [item.source_id for item in github]))
        else:
            outcomes.append(SourceOutcome("GITHUB", "SKIPPED", reason="NO_ENABLED_APPROVED_SOURCES"))

        if heartbeat:
            heartbeat()
        outcomes.append(self._jobs(ingestion, evidence, configured))

        evidence_ids = tuple(_live_evidence_since(self.database_url, started_at, tracked_source_ids))
        return LiveCollectionResult(tuple(outcomes), evidence_ids, tracked_source_ids, started_at)

    def _writing(self, ingestion, evidence, source_ids: list[str]) -> SourceOutcome:
        summary = WritingCollection(ingestion, evidence, self.feed_fetcher).run(source_ids)
        return _outcome("TECHNICAL_WRITING", summary, source_ids)

    def _github(self, ingestion, evidence, source_ids: list[str]) -> SourceOutcome:
        summary = GitHubIngestionRunner(ingestion, evidence, self.github_fetcher).run(source_ids=source_ids)
        return _outcome("GITHUB", summary, source_ids)

    def _jobs(self, ingestion, evidence, configured) -> SourceOutcome:
        try:
            policy = load_policy(self.job_policy_path)
        except (OSError, ValueError, JobPolicyError) as exc:
            return SourceOutcome("JOBS", "FAILED", reason=f"JOB_POLICY_ERROR:{type(exc).__name__}")
        configured_jobs = {item.source_id: item for item in configured if item.source_type == SourceType.JOBS and item.enabled}
        eligible = [item for item in policy.sources if item.source_kind != "USER_URL" and item.enabled and item.source_id in configured_jobs]
        if self.job_source_id:
            eligible = [item for item in eligible if item.source_id == self.job_source_id]
            if not eligible:
                return SourceOutcome("JOBS", "FAILED", reason="JOB_SOURCE_NOT_ENABLED_OR_NOT_IN_POLICY")
        if not eligible:
            return SourceOutcome("JOBS", "SKIPPED", reason="NO_ENABLED_APPROVED_SOURCES")
        if len(eligible) > 1:
            return SourceOutcome("JOBS", "SKIPPED", tuple(item.source_id for item in eligible), reason="MULTIPLE_JOB_SOURCES_REQUIRE_EXPLICIT_SELECTION")
        source = eligible[0]
        try:
            report = JobCollectionRunner(ingestion, evidence, policy, self.job_fetcher).run(source_ids=[source.source_id])
        except Exception as exc:
            return SourceOutcome("JOBS", "FAILED", (source.source_id,), reason=f"JOB_COLLECTION_ERROR:{type(exc).__name__}")
        return _outcome("JOBS", report.summary, [source.source_id])


class WritingCollection:
    """Small adapter that keeps the writing runner import local to this seam."""

    def __init__(self, ingestion, evidence, fetcher):
        from .writing_ingestion import WritingIngestionRunner

        self.runner = WritingIngestionRunner(ingestion, evidence, fetcher)

    def run(self, source_ids: list[str]) -> CollectionSummary:
        return self.runner.run(source_ids=source_ids, source_type=SourceType.TECHNICAL_WRITING, policy_version="writing-rss-v1")


def run_live_pipeline(
    database_url: str,
    *,
    run_date: date,
    policy_version: str,
    resume: bool = False,
    collector: LiveSourceCollector | None = None,
    job_source_id: str | None = None,
    replay_evidence_ids: tuple[str, ...] | None = None,
    replay_since: datetime | None = None,
) -> dict[str, Any]:
    """Run one live collection-to-publication cycle with durable stages."""

    repository = PipelineRepository(database_url)
    mode = "live-replay" if replay_evidence_ids is not None else "live"
    claim = repository.claim(run_date, policy_version, resume=resume, mode=mode)
    run_id, claimed = claim
    if not claimed:
        report = repository.report(run_id)
        report.update({"noop": True, "reason": claim.reason})
        return report

    base_report = repository.report(run_id)
    started_at = datetime.fromisoformat(base_report["created_at"])
    evidence_since = replay_since or started_at
    collection: LiveCollectionResult | None = None
    source_ids = tuple(_collection_source_ids_since(database_url, started_at))
    evidence_ids = tuple(_live_evidence_since(database_url, started_at, source_ids))
    receipt_ids: tuple[str, ...] = ()
    candidates: tuple[CandidateContext, ...] = ()
    capability_count = 0
    source_outcomes: tuple[SourceOutcome, ...] = ()
    published_status = "EMPTY"

    for stage in STAGES:
        if not repository.begin_stage(run_id, stage, lease_owner=claim.lease_owner):
            continue
        started = datetime.now(timezone.utc)
        try:
            if stage == "COLLECT":
                if replay_evidence_ids is not None:
                    evidence_ids = tuple(_live_evidence_ids(database_url, replay_evidence_ids, replay_since))
                    source_ids = tuple(_source_ids_for_evidence(database_url, evidence_ids))
                    source_outcomes = (SourceOutcome("LIVE_REPLAY", "SUCCEEDED", source_ids, stored=len(evidence_ids)),)
                    counts = (len(evidence_ids), len(evidence_ids), 0)
                else:
                    collection = (collector or LiveSourceCollector(database_url, job_source_id=job_source_id)).collect(
                        heartbeat=lambda: repository.heartbeat(run_id, claim.lease_owner)
                    )
                    source_outcomes = collection.outcomes
                    evidence_ids = collection.evidence_ids
                    source_ids = collection.source_ids
                    if collection.failure_count and not collection.success_count and evidence_ids == ():
                        raise LiveWorkerError("all enabled source collections failed")
                    counts = (collection.attempted_count, len(evidence_ids), collection.failure_count)
                repository.set_report_context(
                    run_id,
                    {
                        "source_outcomes": [item.to_dict() for item in source_outcomes],
                        "origin_counts": {"LIVE": len(evidence_ids)},
                        "live_evidence_count": len(evidence_ids),
                    },
                )
            elif stage == "RECEIPT":
                receipt_summary = ReceiptProcessor(EvidenceRepository(database_url), ReceiptRepository(database_url), LiveHeuristicExtractor()).process(list(evidence_ids))
                receipt_ids = tuple(_receipt_ids(database_url, evidence_ids))
                counts = (len(evidence_ids), len(receipt_ids), receipt_summary.failed_validation + receipt_summary.failed_transient)
            elif stage == "CAPABILITY":
                normalized = NormalizationService(ReceiptRepository(database_url), CapabilityRepository(database_url), DeterministicNormalizer()).normalize(list(receipt_ids), limit=20)
                capability_count = len(normalized.mappings)
                counts = (len(receipt_ids), len(normalized.mappings), 0)
            elif stage == "PROFILE":
                capability_ids = _capability_ids(database_url, receipt_ids)
                for capability_id in capability_ids:
                    ProfileRepository(database_url).assess(capability_id)
                counts = (len(capability_ids), len(capability_ids), 0)
            elif stage == "SIGNAL":
                observations = _observations(database_url, receipt_ids, evidence_since)
                if observations:
                    # Published items often predate the fetch by hours or days.
                    # Use the observation window for ranking rather than
                    # dropping valid newly collected evidence at the lower
                    # bound; recency is still calculated from published_at.
                    signal_window_start = min(item.observed_at for item in observations)
                    ranked = SignalRanker(SignalRepository(database_url)).rank(observations, window_start=signal_window_start, window_end=datetime.now(timezone.utc))
                    candidates = tuple(_candidates(database_url, ranked.candidates, receipt_ids))
                    counts = (len(observations), len(candidates), 0)
                else:
                    counts = (0, 0, 0)
            elif stage == "RIFF":
                counts = (len(candidates), len(candidates), 0)
            else:
                result = DailyRiffService(RiffRepository(database_url), DeterministicReasoningProvider(), policy_version=policy_version, max_candidates=5, max_riffs=3).generate(run_date, candidates)
                published_status = "SUCCEEDED" if result.status == "COMPLETED" else "EMPTY"
                counts = (len(candidates), len(result.riffs), 0)
                repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], error_count=counts[2], model_calls=result.provider_calls, duration_ms=_duration_ms(started), lease_owner=claim.lease_owner)
                continue
            repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], error_count=counts[2], duration_ms=_duration_ms(started), lease_owner=claim.lease_owner)
        except Exception as exc:
            repository.set_report_context(run_id, {"source_outcomes": [item.to_dict() for item in source_outcomes], "origin_counts": {"LIVE": len(evidence_ids)}})
            repository.fail_stage(run_id, stage, str(exc), lease_owner=claim.lease_owner)
            report = repository.report(run_id)
            report.update({"receipt_count": len(receipt_ids), "capability_mapping_count": capability_count, "candidate_count": len(candidates), "evidence_outcome": _outcome_classification(len(evidence_ids), len(receipt_ids), capability_count, len(candidates), "FAILED")})
            return report

    repository.set_report_context(run_id, {"source_outcomes": [item.to_dict() for item in source_outcomes], "origin_counts": {"LIVE": len(evidence_ids)}, "live_evidence_count": len(evidence_ids), "receipt_count": len(receipt_ids), "capability_mapping_count": capability_count, "candidate_count": len(candidates), "evidence_outcome": _outcome_classification(len(evidence_ids), len(receipt_ids), capability_count, len(candidates), published_status)})
    repository.complete_run(run_id, published_status, lease_owner=claim.lease_owner)
    report = repository.report(run_id)
    return report


def _outcome(source_type: str, summary: CollectionSummary, source_ids: list[str]) -> SourceOutcome:
    status = summary.status.value if isinstance(summary.status, RunStatus) else str(summary.status)
    return SourceOutcome(source_type, status, tuple(source_ids), summary.run_id, summary.stored, summary.duplicates, summary.skipped, summary.failed_transient, summary.failed_permanent)


def _duration_ms(started: datetime) -> int:
    return max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))


def _outcome_classification(evidence_count: int, receipt_count: int, capability_count: int, candidate_count: int, status: str) -> str:
    if status == "SUCCEEDED":
        return "SUCCEEDED"
    if evidence_count == 0:
        return "SOURCE_UNAVAILABLE"
    if receipt_count and capability_count == 0:
        return "EXTRACTION_FAILURE"
    if capability_count and candidate_count == 0:
        return "INSUFFICIENT_EVIDENCE"
    if candidate_count:
        return "INSUFFICIENT_EVIDENCE"
    return "EMPTY"


def _live_evidence_since(database_url: str, since: datetime, source_ids: tuple[str, ...] | list[str] | None = None) -> list[str]:
    from .db import connection

    with connection(database_url) as conn:
        if source_ids is not None and source_ids:
            rows = conn.execute(
                "SELECT e.evidence_id FROM evidence_versions e JOIN source_items si ON si.source_item_id = e.source_item_id WHERE e.retrieved_at >= %s AND si.source_id = ANY(%s) AND COALESCE(e.data_origin, 'UNCLASSIFIED') = 'LIVE' ORDER BY e.retrieved_at, e.evidence_id",
                (since, list(source_ids)),
            ).fetchall()
        elif source_ids is not None:
            rows = []
        else:
            rows = conn.execute(
                "SELECT e.evidence_id FROM evidence_versions e WHERE e.retrieved_at >= %s AND COALESCE(e.data_origin, 'UNCLASSIFIED') = 'LIVE' ORDER BY e.retrieved_at, e.evidence_id",
                (since,),
            ).fetchall()
    return [str(row[0]) for row in rows]


def _live_evidence_ids(
    database_url: str,
    evidence_ids: tuple[str, ...] | None = None,
    since: datetime | None = None,
    *,
    limit: int = 500,
) -> list[str]:
    """Return only persisted LIVE evidence eligible for replay."""

    from .db import connection

    clauses = ["COALESCE(data_origin, 'UNCLASSIFIED') = 'LIVE'"]
    params: list[Any] = []
    if evidence_ids is not None:
        clauses.append("evidence_id = ANY(%s)")
        params.append(list(evidence_ids))
    if since is not None:
        clauses.append("retrieved_at >= %s")
        params.append(since)
    params.append(limit)
    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT evidence_id FROM evidence_versions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY retrieved_at, evidence_id LIMIT %s",
            params,
        ).fetchall()
    return [str(row[0]) for row in rows]


def _source_ids_for_evidence(database_url: str, evidence_ids: tuple[str, ...] | list[str]) -> list[str]:
    if not evidence_ids:
        return []
    from .db import connection

    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT DISTINCT si.source_id FROM evidence_versions e "
            "JOIN source_items si ON si.source_item_id = e.source_item_id "
            "WHERE e.evidence_id = ANY(%s) ORDER BY si.source_id",
            (list(evidence_ids),),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _collection_source_ids_since(database_url: str, since: datetime) -> list[str]:
    from .db import connection

    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT source_ids FROM collection_runs WHERE started_at >= %s ORDER BY started_at",
            (since,),
        ).fetchall()
    source_ids: list[str] = []
    for (raw_ids,) in rows:
        values = _json_list(raw_ids)
        source_ids.extend(str(value) for value in values)
    return sorted(set(source_ids))


def _receipt_ids(database_url: str, evidence_ids: tuple[str, ...]) -> list[str]:
    if not evidence_ids:
        return []
    from .db import connection

    with connection(database_url) as conn:
        rows = conn.execute("SELECT receipt_id FROM evidence_receipts WHERE evidence_id = ANY(%s) AND status = 'SUCCEEDED' ORDER BY created_at, receipt_id", (list(evidence_ids),)).fetchall()
    return [str(row[0]) for row in rows]


def _capability_ids(database_url: str, receipt_ids: tuple[str, ...]) -> list[str]:
    if not receipt_ids:
        return []
    from .db import connection

    with connection(database_url) as conn:
        rows = conn.execute("SELECT DISTINCT entity_id FROM capability_mappings WHERE receipt_id = ANY(%s) AND entity_type = 'CAPABILITY' AND entity_id IS NOT NULL AND status IN ('ACCEPTED', 'PROPOSED') ORDER BY entity_id", (list(receipt_ids),)).fetchall()
    return [str(row[0]) for row in rows]


def _observations(database_url: str, receipt_ids: tuple[str, ...], since: datetime) -> list[SignalObservation]:
    if not receipt_ids:
        return []
    from .db import connection

    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT e.evidence_id, m.entity_id, m.receipt_id, r.source_metadata, r.uncertainty,
                      e.retrieved_at, e.published_at, s.source_type, s.canonical_root,
                      si.canonical_url
               FROM capability_mappings m
               JOIN evidence_receipts r ON r.receipt_id = m.receipt_id
               JOIN evidence_versions e ON e.evidence_id = r.evidence_id
               JOIN source_items si ON si.source_item_id = e.source_item_id
               JOIN sources s ON s.source_id = si.source_id
               WHERE m.receipt_id = ANY(%s) AND m.entity_type = 'CAPABILITY'
                 AND m.entity_id IS NOT NULL AND m.status IN ('ACCEPTED', 'PROPOSED')
                 AND r.status = 'SUCCEEDED' AND COALESCE(e.data_origin, 'UNCLASSIFIED') = 'LIVE'
                 AND e.retrieved_at >= %s""",
            (list(receipt_ids), since),
        ).fetchall()
    observations: list[SignalObservation] = []
    for evidence_id, capability_id, receipt_id, metadata, uncertainty, retrieved_at, published_at, source_type, root, canonical_url in rows:
        metadata = _json(metadata)
        uncertainty = _json(uncertainty)
        observed_at = published_at or retrieved_at
        observations.append(SignalObservation(
            evidence_id=str(evidence_id), capability_id=str(capability_id), observed_at=observed_at,
            source_type=str(source_type), organization=_text(metadata.get("organization") or metadata.get("organization_at_publication")),
            repository=_text(metadata.get("provider_repository_id")), author=_text(metadata.get("author") or metadata.get("person_name")),
            root_source=_text(metadata.get("source_root") or metadata.get("canonical_root") or root or canonical_url),
            quality=0.75 if uncertainty else 1.0, relevance=1.0,
        ))
    return observations


def _candidates(database_url: str, ranked, receipt_ids: tuple[str, ...]) -> list[CandidateContext]:
    from .db import connection

    if not ranked:
        return []
    with connection(database_url) as conn:
        rows = conn.execute("SELECT m.entity_id, m.receipt_id, r.summary FROM capability_mappings m JOIN evidence_receipts r ON r.receipt_id = m.receipt_id WHERE m.receipt_id = ANY(%s) AND m.entity_type = 'CAPABILITY' AND m.entity_id IS NOT NULL AND m.status IN ('ACCEPTED', 'PROPOSED') ORDER BY m.entity_id, m.receipt_id", (list(receipt_ids),)).fetchall()
        tech_rows = conn.execute("SELECT cr.capability_id, t.name FROM capability_relationships cr JOIN technologies t ON t.technology_id = cr.technology_id WHERE cr.capability_id = ANY(%s) AND cr.status = 'ACTIVE' ORDER BY cr.capability_id, t.name", ([item.capability_id for item in ranked],)).fetchall()
    by_cap: dict[str, list[tuple[str, str]]] = {}
    for capability_id, receipt_id, summary in rows:
        by_cap.setdefault(str(capability_id), []).append((str(receipt_id), str(summary)))
    technologies: dict[str, list[str]] = {}
    for capability_id, name in tech_rows:
        technologies.setdefault(str(capability_id), []).append(str(name))
    result: list[CandidateContext] = []
    for item in ranked:
        source_receipts = by_cap.get(item.capability_id, [])
        result.append(CandidateContext(
            candidate_id=f"live:{item.signal_id}", capability_id=item.capability_id, score=item.score,
            classification=item.classification,
            observation=source_receipts[0][1] if source_receipts else f"Live evidence points to {item.capability_id}.",
            receipt_ids=tuple(receipt_id for receipt_id, _ in source_receipts[:5]),
            profile_state=_profile_state(database_url, item.capability_id),
            associated_technologies=tuple(technologies.get(item.capability_id, [])),
        ))
    return result


def _profile_state(database_url: str, capability_id: str) -> str:
    return ProfileRepository(database_url).assess(capability_id).classification


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, str)):
        try:
            parsed = json.loads(value.decode() if isinstance(value, bytes) else value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, (bytes, str)):
        try:
            parsed = json.loads(value.decode() if isinstance(value, bytes) else value)
            return list(parsed) if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
