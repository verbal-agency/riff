"""Validated, cache-aware Evidence Receipt extraction."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceRecord, EvidenceValidationError, SourceType
from .evidence_repository import EvidenceRepository


SCHEMA_VERSION = 1


class ReceiptValidationError(ValueError):
    """Extractor output is malformed or cannot be grounded in raw evidence."""


class TransientExtractionError(RuntimeError):
    """An extraction provider failure that is safe to retry."""


class ReceiptExtractor(Protocol):
    version: str

    def extract(self, evidence: EvidenceRecord) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    receipt_id: str
    evidence_id: str
    content_hash: str
    extractor_version: str
    schema_version: int
    status: str
    summary: str
    relevant_spans: list[dict[str, Any]]
    capability_candidates: list[str]
    technology_candidates: list[str]
    claims: list[dict[str, Any]]
    signal_strength: dict[str, Any]
    source_metadata: dict[str, Any]
    uncertainty: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReceiptProcessResult:
    evidence_id: str
    status: str
    receipt_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ReceiptProcessSummary:
    processed: int
    cached: int
    failed_validation: int
    failed_transient: int
    results: list[ReceiptProcessResult]


class ReceiptRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def cached(self, evidence_id: str, content_hash: str, extractor_version: str) -> EvidenceReceipt | None:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT receipt_id, evidence_id, content_hash, extractor_version, schema_version, status, summary, "
                "relevant_spans, capability_candidates, technology_candidates, claims, signal_strength, source_metadata, uncertainty "
                "FROM evidence_receipts WHERE evidence_id = %s AND content_hash = %s AND extractor_version = %s AND status = 'SUCCEEDED'",
                (evidence_id, content_hash, extractor_version),
            ).fetchone()
        return self._receipt(row) if row else None

    def get_receipt(self, receipt_id: str, *, include_raw: bool = False) -> EvidenceReceipt | None:
        # `include_raw` is deliberately accepted for a stable downstream API;
        # receipts never load raw evidence themselves.
        del include_raw
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT receipt_id, evidence_id, content_hash, extractor_version, schema_version, status, summary, "
                "relevant_spans, capability_candidates, technology_candidates, claims, signal_strength, source_metadata, uncertainty "
                "FROM evidence_receipts WHERE receipt_id = %s",
                (receipt_id,),
            ).fetchone()
        return self._receipt(row) if row else None

    def list_receipts(self, *, evidence_id: str | None = None, limit: int = 100) -> list[EvidenceReceipt]:
        if limit < 1 or limit > 500:
            raise EvidenceValidationError("limit must be between 1 and 500")
        clause = "WHERE evidence_id = %s" if evidence_id else ""
        params = [evidence_id] if evidence_id else []
        params.append(limit)
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT receipt_id, evidence_id, content_hash, extractor_version, schema_version, status, summary, "
                "relevant_spans, capability_candidates, technology_candidates, claims, signal_strength, source_metadata, uncertainty "
                f"FROM evidence_receipts {clause} ORDER BY created_at DESC LIMIT %s",
                params,
            ).fetchall()
        return [self._receipt(row) for row in rows]

    def start_attempt(self, evidence_id: str, content_hash: str, extractor_version: str, prompt_schema_version: str) -> str:
        attempt_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO receipt_attempts (attempt_id, evidence_id, content_hash, extractor_version, prompt_schema_version, status, started_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (attempt_id, evidence_id, content_hash, extractor_version, prompt_schema_version, "RUNNING", datetime.now(timezone.utc)),
            )
        return attempt_id

    def finish_attempt(self, attempt_id: str, status: str, *, error_code: str | None = None) -> None:
        if status not in {"SUCCEEDED", "FAILED_VALIDATION", "FAILED_TRANSIENT", "SKIPPED_CACHED"}:
            raise ReceiptValidationError(f"invalid receipt attempt status: {status}")
        with connection(self.database_url) as conn:
            result = conn.execute(
                "UPDATE receipt_attempts SET status = %s, error_code = %s, finished_at = %s WHERE attempt_id = %s AND finished_at IS NULL",
                (status, error_code, datetime.now(timezone.utc), attempt_id),
            )
            if result.rowcount != 1:
                raise ReceiptValidationError("receipt attempt is missing or already finished")

    def store(self, receipt: EvidenceReceipt) -> None:
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO evidence_receipts
                (receipt_id, evidence_id, content_hash, extractor_version, schema_version, status,
                 summary, relevant_spans, capability_candidates, technology_candidates, claims,
                 signal_strength, source_metadata, uncertainty)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id, content_hash, extractor_version) DO NOTHING
                """,
                (
                    receipt.receipt_id,
                    receipt.evidence_id,
                    receipt.content_hash,
                    receipt.extractor_version,
                    receipt.schema_version,
                    receipt.status,
                    receipt.summary,
                    Jsonb(receipt.relevant_spans),
                    Jsonb(receipt.capability_candidates),
                    Jsonb(receipt.technology_candidates),
                    Jsonb(receipt.claims),
                    Jsonb(receipt.signal_strength),
                    Jsonb(receipt.source_metadata),
                    Jsonb(receipt.uncertainty),
                ),
            )

    @staticmethod
    def _receipt(row: tuple[Any, ...]) -> EvidenceReceipt:
        values = [json.loads(value.decode() if isinstance(value, bytes) else value) if isinstance(value, (bytes, str)) and index >= 7 else value for index, value in enumerate(row)]
        return EvidenceReceipt(
            receipt_id=_text(values[0]), evidence_id=_text(values[1]), content_hash=_text(values[2]),
            extractor_version=_text(values[3]), schema_version=int(values[4]), status=_text(values[5]),
            summary=_text(values[6]), relevant_spans=values[7], capability_candidates=values[8],
            technology_candidates=values[9], claims=values[10], signal_strength=values[11],
            source_metadata=values[12], uncertainty=values[13],
        )


class KeywordExtractor:
    """Deterministic baseline extractor used for local smoke runs."""

    version = "keyword-v1"

    def extract(self, evidence: EvidenceRecord) -> Mapping[str, Any]:
        if not evidence.raw_content:
            raise ReceiptValidationError("raw evidence body is unavailable")
        text = evidence.raw_content
        excerpt = text[: min(len(text), 240)]
        return {
            "summary": excerpt,
            "relevant_spans": [{"span_id": "summary", "start": 0, "end": len(excerpt), "excerpt": excerpt}],
            "capability_candidates": [],
            "technology_candidates": [],
            "claims": [{"text": excerpt, "span_ids": ["summary"], "claim_type": "OBSERVATION", "uncertainty": {}}],
            "signal_strength": {},
            "source_metadata": {"evidence_id": evidence.evidence_id, "source_id": evidence.source_id, "source_type": evidence.source_type.value},
            "uncertainty": {},
        }


class ReceiptProcessor:
    def __init__(self, evidence: EvidenceRepository, receipts: ReceiptRepository, extractor: ReceiptExtractor, *, prompt_schema_version: str = "receipt-schema-v1"):
        self.evidence = evidence
        self.receipts = receipts
        self.extractor = extractor
        self.prompt_schema_version = prompt_schema_version

    def process(self, evidence_ids: list[str], *, force: bool = False) -> ReceiptProcessSummary:
        processed = cached = failed_validation = failed_transient = 0
        results: list[ReceiptProcessResult] = []
        for evidence_id in evidence_ids:
            record = self.evidence.get_evidence(evidence_id, include_raw=True)
            if record is None:
                results.append(ReceiptProcessResult(evidence_id, "FAILED_VALIDATION", error_code="UNKNOWN_EVIDENCE"))
                failed_validation += 1
                continue
            if not force and self.receipts.cached(record.evidence_id, record.content_hash, self.extractor.version):
                cached += 1
                results.append(ReceiptProcessResult(evidence_id, "SKIPPED_CACHED"))
                continue
            attempt_id = self.receipts.start_attempt(record.evidence_id, record.content_hash, self.extractor.version, self.prompt_schema_version)
            try:
                output = self.extractor.extract(record)
                receipt = validate_receipt_output(record, output, self.extractor.version)
                self.receipts.store(receipt)
                self.receipts.finish_attempt(attempt_id, "SUCCEEDED")
                processed += 1
                results.append(ReceiptProcessResult(evidence_id, "SUCCEEDED", receipt.receipt_id))
            except TransientExtractionError as exc:
                self.receipts.finish_attempt(attempt_id, "FAILED_TRANSIENT", error_code=type(exc).__name__.upper())
                failed_transient += 1
                results.append(ReceiptProcessResult(evidence_id, "FAILED_TRANSIENT", error_code=type(exc).__name__.upper()))
            except (ReceiptValidationError, EvidenceValidationError, ValueError) as exc:
                self.receipts.finish_attempt(attempt_id, "FAILED_VALIDATION", error_code=type(exc).__name__.upper())
                failed_validation += 1
                results.append(ReceiptProcessResult(evidence_id, "FAILED_VALIDATION", error_code=type(exc).__name__.upper()))
        return ReceiptProcessSummary(processed, cached, failed_validation, failed_transient, results)


def validate_receipt_output(evidence: EvidenceRecord, output: Mapping[str, Any], extractor_version: str) -> EvidenceReceipt:
    if not isinstance(output, Mapping):
        raise ReceiptValidationError("receipt output must be an object")
    required = ("summary", "relevant_spans", "capability_candidates", "technology_candidates", "claims", "signal_strength", "source_metadata", "uncertainty")
    missing = [key for key in required if key not in output]
    if missing:
        raise ReceiptValidationError(f"receipt output missing fields: {','.join(missing)}")
    summary = output["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ReceiptValidationError("summary must be a non-empty string")
    spans = output["relevant_spans"]
    if not isinstance(spans, list):
        raise ReceiptValidationError("relevant_spans must be a list")
    span_ids: set[str] = set()
    raw = evidence.raw_content or ""
    for span in spans:
        if not isinstance(span, Mapping) or not isinstance(span.get("span_id"), str):
            raise ReceiptValidationError("each relevant span requires span_id")
        if span["span_id"] in span_ids:
            raise ReceiptValidationError("span IDs must be unique")
        span_ids.add(span["span_id"])
        start, end, excerpt = span.get("start"), span.get("end"), span.get("excerpt")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(excerpt, str) or start < 0 or end <= start or end > len(raw) or raw[start:end] != excerpt:
            raise ReceiptValidationError("relevant span is outside or mismatched with raw evidence")
    capabilities = _string_list(output["capability_candidates"], "capability_candidates")
    technologies = _string_list(output["technology_candidates"], "technology_candidates")
    claims = output["claims"]
    if not isinstance(claims, list):
        raise ReceiptValidationError("claims must be a list")
    for claim in claims:
        if not isinstance(claim, Mapping) or not isinstance(claim.get("text"), str) or not isinstance(claim.get("span_ids"), list):
            raise ReceiptValidationError("each claim requires text and span_ids")
        if any(span_id not in span_ids for span_id in claim["span_ids"]):
            raise ReceiptValidationError("claim cites an unknown span")
    source_metadata = output["source_metadata"]
    if not isinstance(source_metadata, Mapping) or source_metadata.get("evidence_id") != evidence.evidence_id or source_metadata.get("source_id") != evidence.source_id:
        raise ReceiptValidationError("source_metadata does not match evidence")
    if not isinstance(output["signal_strength"], Mapping) or not isinstance(output["uncertainty"], Mapping):
        raise ReceiptValidationError("signal_strength and uncertainty must be objects")
    return EvidenceReceipt(
        receipt_id=str(uuid.uuid4()), evidence_id=evidence.evidence_id, content_hash=evidence.content_hash,
        extractor_version=extractor_version, schema_version=SCHEMA_VERSION, status="SUCCEEDED",
        summary=summary, relevant_spans=[dict(span) for span in spans], capability_candidates=capabilities,
        technology_candidates=technologies, claims=[dict(claim) for claim in claims], signal_strength=dict(output["signal_strength"]),
        source_metadata=dict(source_metadata), uncertainty=dict(output["uncertainty"]),
    )


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReceiptValidationError(f"{field} must be a list of non-empty strings")
    return list(value)


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value
