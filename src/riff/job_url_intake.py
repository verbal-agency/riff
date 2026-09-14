"""Single user-submitted job listing URL intake."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .evidence import EvidenceValidationError
from .evidence_repository import EvidenceRepository
from .ingestion_repository import CollectionSummary, IngestionRepository, ItemOutcome, RunStatus
from .job_fetch import (
    HttpJobFetcher,
    JobDecompositionError,
    JobFetcher,
    JobPermanentError,
    JobTransientError,
    decompose_listing,
    validate_target_url,
)
from .job_ingestion import JobIngestionRunner
from .job_source_policy import JobPolicyError, JobSourcePolicy
from .job_collection import source_run_lock


class JobUrlIntakeRunner:
    def __init__(self, ingestion: IngestionRepository, evidence: EvidenceRepository, policy: JobSourcePolicy, fetcher: JobFetcher | None = None, *, content_limit: int = 20_000):
        self.ingestion = ingestion
        self.evidence = evidence
        self.policy = policy
        self.fetcher = fetcher or HttpJobFetcher()
        self.importer = JobIngestionRunner(ingestion, evidence, content_limit=content_limit)

    def run(self, url: str, *, source_id: str, dry_run: bool = False) -> dict[str, Any]:
        policy_source = self.policy.source(source_id)
        if policy_source.source_kind != "USER_URL":
            raise JobPolicyError("URL intake requires a USER_URL source")
        if not policy_source.enabled:
            raise JobPolicyError("USER_URL source is disabled")
        # This validation runs before a fetcher is invoked, including fixtures.
        resolve_hosts = isinstance(self.fetcher, HttpJobFetcher)
        normalized_url = validate_target_url(url, policy_source, resolve=resolve_hosts)
        response = None
        retries = 0
        for attempt in range(policy_source.retry_policy["max_attempts"] + 1):
            try:
                response = self.fetcher.fetch(normalized_url, policy_source)
                break
            except JobTransientError:
                retries += 1
                if attempt >= policy_source.retry_policy["max_attempts"]:
                    raise
        if response is None:
            raise JobPermanentError("listing request did not complete")
        final_url = validate_target_url(response.final_url, policy_source, resolve=resolve_hosts)
        posting_record = decompose_listing(response.body, final_url=final_url, fetched_at=response.fetched_at, allow_html_fallback=True)
        posting_record["metadata"]["submitted_url"] = normalized_url
        posting_record["metadata"]["final_url"] = final_url
        posting_record["metadata"]["policy_id"] = self.policy.policy_id
        posting_record["metadata"]["retrieved_at"] = response.fetched_at.isoformat()
        posting_record["metadata"]["request_count"] = 1
        posting_record["metadata"]["retry_count"] = retries
        # Store the bounded raw response as evidence while job_postings keeps
        # the normalized decomposition fields for later receipt processing.
        posting_record["description"] = posting_record.get("description") or "Listing snapshot"
        if dry_run:
            return {"status": "DRY_RUN", "source_id": source_id, "url": normalized_url, "final_url": final_url, "posting": posting_record, "request_count": 1, "retry_count": retries}

        with source_run_lock(source_id):
            sources = self.ingestion.list_sources(source_ids=[source_id], source_type="JOBS")
            if len(sources) != 1:
                raise EvidenceValidationError("every URL intake source must be configured as JOBS")
            source = sources[0]
            run = self.ingestion.start_run([source_id], self.policy.policy_id)
            counts = {"stored": 0, "duplicates": 0, "skipped": 0, "failed_transient": 0, "failed_permanent": 0}
            try:
                posting = self.importer._normalize(posting_record, response.fetched_at)
                # Preserve raw HTML in G01 evidence, bounded by the importer limit.
                from dataclasses import replace

                posting = replace(posting, content=response.body.decode("utf-8", errors="replace"))
                evidence_id = self.importer._store(run.run_id, source, posting, counts)
                self.ingestion.update_cursor(source_id, "jobs:url:" + normalized_url, response.fetched_at.isoformat())
                status = RunStatus.SUCCEEDED
            except (JobDecompositionError, JobPermanentError, EvidenceValidationError, ValueError) as exc:
                counts["failed_permanent"] += 1
                self.ingestion.record_item_result(run.run_id, source_id, ItemOutcome.FAILED_PERMANENT, canonical_url=final_url, error_code=type(exc).__name__.upper())
                status = RunStatus.FAILED
            self.ingestion.finish_run(run.run_id, status)
        summary = CollectionSummary(run.run_id, status, **counts)
        return {"status": status, "source_id": source_id, "url": normalized_url, "final_url": final_url, "summary": asdict(summary), "request_count": 1, "retry_count": retries, "synthesis_receipt": {"source_id": source_id, "canonical_url": final_url, "evidence_ids": [evidence_id] if status == RunStatus.SUCCEEDED else []}}
