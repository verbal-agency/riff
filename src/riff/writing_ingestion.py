"""Incremental curated technical-writing collection runner."""

from __future__ import annotations

from .evidence import EvidenceSubmission
from .evidence_repository import EvidenceRepository
from .ingestion import FeedEntry, FeedError, FeedFetcher, PermanentFeedError, TransientFeedError, cursor_marker, marker_after, parse_feed
from .ingestion_repository import (
    CollectionSummary,
    IngestionRepository,
    ItemOutcome,
    RunStatus,
)


class WritingIngestionRunner:
    def __init__(self, ingestion: IngestionRepository, evidence: EvidenceRepository, fetcher: FeedFetcher):
        self.ingestion = ingestion
        self.evidence = evidence
        self.fetcher = fetcher

    def run(
        self,
        *,
        source_ids: list[str] | None = None,
        source_type=None,
        policy_version: str = "writing-rss-v1",
    ) -> CollectionSummary:
        sources = self.ingestion.list_sources(source_ids=source_ids, source_type=source_type)
        run = self.ingestion.start_run([source.source_id for source in sources], policy_version)
        counts = {"stored": 0, "duplicates": 0, "skipped": 0, "failed_transient": 0, "failed_permanent": 0}
        any_failure = False
        any_success = False
        try:
            for source in sources:
                if not source.enabled:
                    self.ingestion.record_item_result(run.run_id, source.source_id, ItemOutcome.SKIPPED, error_code="SOURCE_DISABLED")
                    counts["skipped"] += 1
                    continue
                try:
                    response = self.fetcher.fetch(source.endpoint)
                    entries = parse_feed(response.body, fetched_at=response.fetched_at, base_url=response.final_url)
                    cursor = self.ingestion.get_cursor(source.source_id, source.cursor_kind)
                    self._collect_source(run.run_id, source, entries, cursor, counts)
                    any_success = True
                except TransientFeedError as exc:
                    any_failure = True
                    counts["failed_transient"] += 1
                    self.ingestion.record_item_result(
                        run.run_id, source.source_id, ItemOutcome.FAILED_TRANSIENT, error_code=_error_code(exc)
                    )
                except (PermanentFeedError, FeedError) as exc:
                    any_failure = True
                    counts["failed_permanent"] += 1
                    self.ingestion.record_item_result(
                        run.run_id, source.source_id, ItemOutcome.FAILED_PERMANENT, error_code=_error_code(exc)
                    )
            any_failure = any_failure or bool(
                counts["failed_transient"] or counts["failed_permanent"]
            )
            status = RunStatus.PARTIAL if any_failure and any_success else RunStatus.FAILED if any_failure else RunStatus.SUCCEEDED
            self.ingestion.finish_run(run.run_id, status)
        except Exception:
            # Leave a durable RUNNING record when an unexpected process failure
            # occurs; the cursor has only advanced after completed item writes.
            raise
        return CollectionSummary(run.run_id, status, **counts)

    def _collect_source(self, run_id, source, entries: list[FeedEntry], cursor: str | None, counts: dict[str, int]) -> None:
        current_cursor = cursor
        for entry in entries:
            if not marker_after(entry, current_cursor):
                continue
            try:
                if not entry.link:
                    self.ingestion.record_item_result(
                        run_id,
                        source.source_id,
                        ItemOutcome.FAILED_PERMANENT,
                        source_native_id=entry.native_id or None,
                        error_code="MISSING_LINK",
                    )
                    counts["failed_permanent"] += 1
                    current_cursor = cursor_marker(entry)
                    self.ingestion.update_cursor(source.source_id, source.cursor_kind, current_cursor)
                    continue
                raw_content = entry.content or entry.raw_xml
                submission = EvidenceSubmission(
                    source_id=source.source_id,
                    canonical_url=entry.link,
                    native_id=entry.native_id,
                    title=entry.title,
                    published_at=entry.observed_at,
                    raw_content=raw_content,
                    retrieval_metadata={"adapter": "rss_atom", "config_version": source.config_version},
                )
                result = self.evidence.ingest(submission)
                outcome = ItemOutcome.STORED if result.created else ItemOutcome.DUPLICATE
                self.ingestion.record_item_result(
                    run_id,
                    source.source_id,
                    outcome,
                    canonical_url=entry.link,
                    source_native_id=entry.native_id,
                    evidence_id=result.evidence_id,
                )
                counts["stored" if result.created else "duplicates"] += 1
                current_cursor = cursor_marker(entry)
                # The evidence transaction has committed before this cursor write.
                self.ingestion.update_cursor(source.source_id, source.cursor_kind, current_cursor)
            except Exception as exc:
                if isinstance(exc, TransientFeedError):
                    outcome = ItemOutcome.FAILED_TRANSIENT
                    counts["failed_transient"] += 1
                else:
                    outcome = ItemOutcome.FAILED_PERMANENT
                    counts["failed_permanent"] += 1
                self.ingestion.record_item_result(
                    run_id,
                    source.source_id,
                    outcome,
                    canonical_url=entry.link,
                    source_native_id=entry.native_id,
                    error_code=_error_code(exc),
                )
                # Permanent malformed/item validation is quarantined and can move
                # the cursor; transient failures remain retryable.
                if outcome == ItemOutcome.FAILED_PERMANENT:
                    current_cursor = cursor_marker(entry)
                    self.ingestion.update_cursor(source.source_id, source.cursor_kind, current_cursor)


def _error_code(error: Exception) -> str:
    return type(error).__name__.upper()
