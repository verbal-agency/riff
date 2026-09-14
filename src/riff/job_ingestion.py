"""Offline-first job-market import with reversible employer identity handling."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceSubmission, EvidenceValidationError, canonicalize_url
from .evidence_repository import EvidenceRepository
from .ingestion_repository import CollectionSummary, IngestionRepository, ItemOutcome, RunStatus


class JobImportError(ValueError):
    """A fixture/import record cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class JobPosting:
    provider_posting_id: str | None
    canonical_url: str
    role_title: str
    company_name: str | None
    employer_id: str | None
    seniority: str | None
    compensation: str | None
    location: str | None
    published_at: datetime | None
    observed_at: datetime
    expired: bool
    content: str
    metadata: dict[str, object]


def load_job_fixture(path: str | Path) -> tuple[datetime, list[Mapping[str, Any]]]:
    """Load schema-versioned JSON without contacting a job provider."""

    fixture_path = Path(path)
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobImportError("job import file could not be read as JSON") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise JobImportError("job import requires schema_version 1")
    observed_at = _parse_time(payload.get("observed_at")) or datetime.now(timezone.utc)
    postings = payload.get("postings")
    if not isinstance(postings, list):
        raise JobImportError("job import requires a postings list")
    return observed_at, postings


class JobMetadataRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def resolve_employer(self, source_id: str, record: Mapping[str, Any], posting_key: str) -> str | None:
        display_name = _optional_text(record.get("company_name") or record.get("employer"))
        if not display_name:
            return None
        normalized = _normalize_name(display_name)
        provider_id = _optional_text(record.get("company_id") or record.get("employer_id"))
        ambiguous = bool(record.get("employer_ambiguous") or record.get("identity_state") == "AMBIGUOUS")
        confidence = _number(record.get("employer_confidence"), default=0.5 if ambiguous else 1.0)
        if ambiguous:
            employer_id = f"job-employer:{source_id}:ambiguous:{_digest(display_name + posting_key)}"
            state = "AMBIGUOUS"
        elif provider_id:
            employer_id = f"job-employer:{source_id}:provider:{_digest(provider_id)}"
            state = "CONFIDENT"
        else:
            employer_id = None
            state = "CONFIDENT"
            with connection(self.database_url) as conn:
                existing = conn.execute(
                    "SELECT employer_id FROM job_employers WHERE source_id = %s "
                    "AND normalized_name = %s AND identity_state = 'CONFIDENT'",
                    (source_id, normalized),
                ).fetchone()
            if existing:
                employer_id = _text(existing[0])
            else:
                employer_id = f"job-employer:{source_id}:name:{_digest(normalized)}"
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO job_employers
                (employer_id, source_id, provider_employer_id, display_name,
                 normalized_name, identity_state, confidence, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (employer_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    provider_employer_id = COALESCE(EXCLUDED.provider_employer_id, job_employers.provider_employer_id),
                    normalized_name = EXCLUDED.normalized_name,
                    identity_state = EXCLUDED.identity_state,
                    confidence = EXCLUDED.confidence,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                (employer_id, source_id, provider_id, display_name, normalized, state, confidence, Jsonb({})),
            )
            alias_status = "CANDIDATE" if ambiguous else "CONFIRMED"
            conn.execute(
                """
                INSERT INTO job_employer_aliases
                (alias_id, employer_id, source_id, alias, normalized_alias, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (employer_id, normalized_alias) DO UPDATE SET status = EXCLUDED.status
                """,
                (_id(), employer_id, source_id, display_name, normalized, alias_status),
            )
        return employer_id

    def record_posting(self, source_id: str, evidence_id: str, posting: JobPosting) -> None:
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO job_postings
                (evidence_id, source_id, provider_posting_id, canonical_url,
                 employer_id, employer_display_name, role_title, seniority,
                 compensation, location, published_at, observed_at, expired, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET
                    employer_id = EXCLUDED.employer_id,
                    employer_display_name = EXCLUDED.employer_display_name,
                    role_title = EXCLUDED.role_title,
                    seniority = EXCLUDED.seniority,
                    compensation = EXCLUDED.compensation,
                    location = EXCLUDED.location,
                    published_at = EXCLUDED.published_at,
                    observed_at = EXCLUDED.observed_at,
                    expired = EXCLUDED.expired,
                    metadata = EXCLUDED.metadata
                """,
                (
                    evidence_id,
                    source_id,
                    posting.provider_posting_id,
                    posting.canonical_url,
                    posting.employer_id,
                    posting.company_name,
                    posting.role_title,
                    posting.seniority,
                    posting.compensation,
                    posting.location,
                    posting.published_at,
                    posting.observed_at,
                    posting.expired,
                    Jsonb(posting.metadata),
                ),
            )


class JobIngestionRunner:
    def __init__(self, ingestion: IngestionRepository, evidence: EvidenceRepository, *, content_limit: int = 20_000):
        if content_limit < 1:
            raise ValueError("content_limit must be positive")
        self.ingestion = ingestion
        self.evidence = evidence
        self.metadata = JobMetadataRepository(ingestion.database_url)
        self.content_limit = content_limit

    def run_file(
        self,
        path: str | Path,
        *,
        source_ids: list[str],
        policy_version: str = "jobs-json-v1",
    ) -> CollectionSummary:
        observed_at, records = load_job_fixture(path)
        sources = self.ingestion.list_sources(source_ids=source_ids, source_type="JOBS")
        if len(sources) != len(source_ids):
            raise EvidenceValidationError("every requested source must be configured as JOBS")
        if len(sources) != 1:
            raise EvidenceValidationError("job import requires exactly one source")
        source = sources[0]
        run = self.ingestion.start_run([source.source_id], policy_version)
        counts = {"stored": 0, "duplicates": 0, "skipped": 0, "failed_transient": 0, "failed_permanent": 0}
        for index, record in enumerate(records):
            try:
                if not isinstance(record, Mapping):
                    raise JobImportError("posting must be an object")
                posting = self._normalize(record, observed_at)
                self._store(run.run_id, source, posting, counts)
            except (JobImportError, EvidenceValidationError) as exc:
                counts["failed_permanent"] += 1
                self.ingestion.record_item_result(
                    run.run_id,
                    source.source_id,
                    ItemOutcome.FAILED_PERMANENT,
                    source_native_id=str(record.get("provider_posting_id")) if isinstance(record, Mapping) and record.get("provider_posting_id") else f"row:{index}",
                    error_code=type(exc).__name__.upper(),
                )
        status = RunStatus.PARTIAL if counts["failed_permanent"] and counts["stored"] else RunStatus.FAILED if counts["failed_permanent"] else RunStatus.SUCCEEDED
        self.ingestion.finish_run(run.run_id, status)
        self.ingestion.update_cursor(source.source_id, source.cursor_kind, json.dumps({"observed_at": observed_at.isoformat(), "rows": len(records)}, sort_keys=True))
        return CollectionSummary(run.run_id, status, **counts)

    def _normalize(self, record: Mapping[str, Any], observed_at: datetime) -> JobPosting:
        title = _optional_text(record.get("role_title") or record.get("title"))
        if not title:
            raise JobImportError("posting role_title is required")
        url = _optional_text(record.get("canonical_url") or record.get("url"))
        if not url:
            raise JobImportError("posting canonical_url is required")
        try:
            canonical_url = canonicalize_url(url)
        except EvidenceValidationError as exc:
            raise JobImportError("posting canonical_url is invalid") from exc
        provider_id = _optional_text(record.get("provider_posting_id") or record.get("id"))
        published_at = _parse_time(record.get("published_at") or record.get("publication_date"))
        actual_observed = _parse_time(record.get("observed_at")) or observed_at
        company_name = _optional_text(record.get("company_name") or record.get("employer"))
        content_parts = [_optional_text(record.get(key)) for key in ("description", "responsibilities")]
        content = "\n\n".join(part for part in content_parts if part)
        if not content:
            content = json.dumps({"role_title": title, "company_name": company_name}, sort_keys=True)
        supplied_metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        return JobPosting(
            provider_posting_id=provider_id,
            canonical_url=canonical_url,
            role_title=title,
            company_name=company_name,
            employer_id=None,
            seniority=_optional_text(record.get("seniority")),
            compensation=_optional_text(record.get("compensation")),
            location=_optional_text(record.get("location")),
            published_at=published_at,
            observed_at=actual_observed,
            expired=bool(record.get("expired", False)),
            content=content,
            metadata={
                "provider": record.get("provider"),
                "source_status": record.get("status"),
                "company_id": record.get("company_id") or record.get("employer_id"),
                "employer_ambiguous": bool(record.get("employer_ambiguous") or record.get("identity_state") == "AMBIGUOUS"),
                "employer_confidence": record.get("employer_confidence"),
                **dict(supplied_metadata),
            },
        )

    def _store(self, run_id: str, source, posting: JobPosting, counts: dict[str, int]) -> str:
        record = {
            "company_name": posting.company_name,
            "employer_id": posting.metadata.get("company_id"),
            "employer_ambiguous": posting.metadata.get("employer_ambiguous"),
            "employer_confidence": posting.metadata.get("employer_confidence"),
        }
        employer_id = self.metadata.resolve_employer(source.source_id, record, posting.provider_posting_id or posting.canonical_url)
        bounded = posting.content[: self.content_limit]
        truncated = len(bounded) < len(posting.content)
        result = self.evidence.ingest(
            EvidenceSubmission(
                source_id=source.source_id,
                canonical_url=posting.canonical_url,
                native_id=posting.provider_posting_id,
                title=posting.role_title,
                published_at=posting.published_at,
                raw_content=bounded,
                snapshot_ref=posting.canonical_url if truncated else None,
                retrieval_metadata={"adapter": "job_json_import", "truncated": truncated, **posting.metadata},
            )
        )
        stored_posting = replace(posting, employer_id=employer_id)
        self.metadata.record_posting(source.source_id, result.evidence_id, stored_posting)
        outcome = ItemOutcome.STORED if result.created else ItemOutcome.DUPLICATE
        self.ingestion.record_item_result(run_id, source.source_id, outcome, canonical_url=posting.canonical_url, source_native_id=posting.provider_posting_id, evidence_id=result.evidence_id)
        counts["stored" if result.created else "duplicates"] += 1
        return result.evidence_id


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: Any, *, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _id() -> str:
    return str(uuid.uuid4())


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value
