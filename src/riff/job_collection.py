"""One-shot, bounded job collection shared by terminal and schedulers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .evidence import EvidenceValidationError
from .evidence_repository import EvidenceRepository
from .ingestion import parse_feed
from .ingestion_repository import CollectionSummary, IngestionRepository, ItemOutcome, RunStatus
from .job_fetch import (
    FixtureJobFetcher,
    HttpJobFetcher,
    JobDecompositionError,
    JobFetcher,
    JobPermanentError,
    JobTransientError,
    decompose_listing,
)
from .job_ingestion import JobImportError, JobIngestionRunner
from .job_source_policy import JobPolicyError, JobSourcePolicy


@dataclass(frozen=True, slots=True)
class JobCollectionReport:
    summary: CollectionSummary
    request_count: int
    retry_count: int
    cursor: str | None
    policy_id: str
    source_id: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"summary": asdict(self.summary), "request_count": self.request_count, "retry_count": self.retry_count, "cursor": self.cursor, "policy_id": self.policy_id, "source_id": self.source_id, "synthesis_receipt": {"evidence_ids": list(self.evidence_ids), "policy_id": self.policy_id}}


class JobCollectionRunner:
    def __init__(self, ingestion: IngestionRepository, evidence: EvidenceRepository, policy: JobSourcePolicy, fetcher: JobFetcher | None = None, *, content_limit: int = 20_000):
        self.ingestion = ingestion
        self.evidence = evidence
        self.policy = policy
        self.fetcher = fetcher or HttpJobFetcher()
        self.importer = JobIngestionRunner(ingestion, evidence, content_limit=content_limit)

    def run(self, *, source_ids: list[str] | None = None, fixture_mode: bool = False, dry_run: bool = False) -> JobCollectionReport:
        lock_key = source_ids[0] if source_ids and len(source_ids) == 1 else "all"
        with source_run_lock(lock_key):
            return self._run_unlocked(source_ids=source_ids, fixture_mode=fixture_mode, dry_run=dry_run)

    def _run_unlocked(self, *, source_ids: list[str] | None = None, fixture_mode: bool = False, dry_run: bool = False) -> JobCollectionReport:
        configured = self.ingestion.list_sources(source_ids=source_ids, source_type="JOBS")
        if source_ids and len(configured) != len(source_ids):
            raise EvidenceValidationError("every requested source must be configured as JOBS")
        candidates = [source for source in configured if source.source_id in {item.source_id for item in self.policy.sources if item.source_kind != "USER_URL"}]
        if len(candidates) != 1:
            raise JobPolicyError("job collection requires exactly one configured policy source")
        source = candidates[0]
        policy_source = self.policy.source(source.source_id)
        if not policy_source.enabled and not fixture_mode:
            raise JobPolicyError("job source is disabled or awaiting review")
        if dry_run:
            return self._dry_run(source, policy_source)
        run = self.ingestion.start_run([source.source_id], self.policy.policy_id)
        counts = {"stored": 0, "duplicates": 0, "skipped": 0, "failed_transient": 0, "failed_permanent": 0}
        requests = retries = 0
        response = None
        for attempt in range(policy_source.retry_policy["max_attempts"] + 1):
            if requests >= policy_source.bounds["max_requests"]:
                break
            requests += 1
            try:
                response = self.fetcher.fetch(policy_source.endpoint or "", policy_source)
                break
            except JobTransientError as exc:
                retries += 1
                if attempt >= policy_source.retry_policy["max_attempts"]:
                    self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.FAILED_TRANSIENT, error_code=type(exc).__name__.upper())
                    counts["failed_transient"] += 1
            except JobPermanentError as exc:
                self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.FAILED_PERMANENT, error_code=type(exc).__name__.upper())
                counts["failed_permanent"] += 1
                break
        if response is not None:
            evidence_ids: list[str] = []
            try:
                observed_at, records = _records_from_response(response.body, response.final_url, response.fetched_at, policy_source)
                if len(records) > policy_source.bounds["max_items"]:
                    raise JobPermanentError("job item bound exceeded")
                for index, record in enumerate(records):
                    try:
                        record.setdefault("metadata", {})
                        record["metadata"].update({
                            "policy_id": self.policy.policy_id,
                            "retrieved_at": response.fetched_at.isoformat(),
                            "raw_snapshot_ref": response.final_url,
                            "raw_content_hash": hashlib.sha256(response.body).hexdigest(),
                            "parser_version": f"job-{policy_source.source_kind.lower()}-v1",
                        })
                        posting = self.importer._normalize(record, observed_at)
                        evidence_ids.append(self.importer._store(run.run_id, source, posting, counts))
                    except (JobImportError, EvidenceValidationError) as exc:
                        counts["failed_permanent"] += 1
                        self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.FAILED_PERMANENT, source_native_id=f"row:{index}", error_code=type(exc).__name__.upper())
                cursor = json.dumps({"body_hash": hashlib.sha256(response.body).hexdigest(), "items": len(records), "observed_at": observed_at.isoformat()}, sort_keys=True)
                self.ingestion.update_cursor(source.source_id, source.cursor_kind, cursor)
            except (JobPermanentError, JobDecompositionError) as exc:
                counts["failed_permanent"] += 1
                self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.FAILED_PERMANENT, error_code=type(exc).__name__.upper())
                cursor = None
        else:
            cursor = None
        status = RunStatus.PARTIAL if counts["failed_permanent"] and counts["stored"] else RunStatus.FAILED if counts["failed_permanent"] or counts["failed_transient"] else RunStatus.SUCCEEDED
        self.ingestion.finish_run(run.run_id, status)
        return JobCollectionReport(CollectionSummary(run.run_id, status, **counts), requests, retries, cursor, self.policy.policy_id, source.source_id, tuple(evidence_ids if response is not None else ()))

    def _dry_run(self, source, policy_source: JobSource) -> JobCollectionReport:
        response = self.fetcher.fetch(policy_source.endpoint or "", policy_source)
        observed_at, records = _records_from_response(response.body, response.final_url, response.fetched_at, policy_source)
        if len(records) > policy_source.bounds["max_items"]:
            raise JobPolicyError("job item bound exceeded")
        for record in records:
            self.importer._normalize(record, observed_at)
        fake = CollectionSummary("dry-run", RunStatus.SUCCEEDED, stored=len(records))
        return JobCollectionReport(fake, 1, 0, json.dumps({"items": len(records), "body_hash": hashlib.sha256(response.body).hexdigest()}, sort_keys=True), self.policy.policy_id, source.source_id)


def dry_run_fixture(policy: JobSourcePolicy, *, source_id: str | None = None, fetcher: JobFetcher | None = None) -> JobCollectionReport:
    """Replay a configured fixture without Postgres, credentials, or network."""

    candidates = [source for source in policy.sources if source.source_kind != "USER_URL"]
    source = policy.source(source_id) if source_id else (candidates[0] if candidates else None)
    if source is None or source.source_kind == "USER_URL":
        raise JobPolicyError("fixture collection requires an API, RSS, or HTML source")
    client = fetcher or FixtureJobFetcher()
    response = client.fetch(source.endpoint or "", source)
    observed_at, records = _records_from_response(response.body, response.final_url, response.fetched_at, source)
    if len(records) > source.bounds["max_items"]:
        raise JobPolicyError("job item bound exceeded")
    importer = JobIngestionRunner(IngestionRepository("postgresql://offline/unused"), EvidenceRepository("postgresql://offline/unused"))
    for record in records:
        importer._normalize(record, observed_at)
    fake = CollectionSummary("dry-run", RunStatus.SUCCEEDED, stored=len(records))
    return JobCollectionReport(fake, 1, 0, json.dumps({"items": len(records), "body_hash": hashlib.sha256(response.body).hexdigest()}, sort_keys=True), policy.policy_id, source.source_id)


def _records_from_response(body: bytes, final_url: str, fetched_at: datetime, source: JobSource) -> tuple[datetime, list[dict[str, Any]]]:
    content_type = ""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("postings"), list):
        observed = _parse_time(payload.get("observed_at")) or fetched_at
        if any(not isinstance(item, Mapping) for item in payload["postings"]):
            raise JobPermanentError("job postings response contains a malformed item")
        return observed, [dict(item) for item in payload["postings"]]
    if isinstance(payload, list):
        if any(not isinstance(item, Mapping) for item in payload):
            raise JobPermanentError("job postings response contains a malformed item")
        return fetched_at, [dict(item) for item in payload]
    if source.source_kind == "RSS":
        entries = parse_feed(body, fetched_at=fetched_at, base_url=final_url)
        return fetched_at, [{"provider_posting_id": item.native_id, "canonical_url": item.link, "role_title": item.title, "description": item.content, "published_at": item.observed_at.isoformat()} for item in entries if item.link and item.title]
    if source.source_kind == "HTML":
        return fetched_at, [decompose_listing(body, final_url=final_url, fetched_at=fetched_at)]
    raise JobPermanentError("job API response must be schema-versioned JSON")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=result.tzinfo or timezone.utc).astimezone(timezone.utc)


@contextmanager
def source_run_lock(source_id: str):
    """Prevent overlapping local runs for the same source."""

    path = os.path.join(tempfile.gettempdir(), f"riff-job-{hashlib.sha256(source_id.encode()).hexdigest()[:16]}.lock")
    handle = open(path, "a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise JobPolicyError("another job run already holds the source lock") from exc
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
