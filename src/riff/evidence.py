"""Domain contracts for provenance-first evidence storage."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class SourceType(str, Enum):
    JOBS = "JOBS"
    GITHUB = "GITHUB"
    TECHNICAL_WRITING = "TECHNICAL_WRITING"
    DISCOVERY = "DISCOVERY"


class RetrievalOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    SKIPPED = "SKIPPED"


class ProvenanceRelationship(str, Enum):
    DISCOVERED_THROUGH = "DISCOVERED_THROUGH"
    VERSION_OF = "VERSION_OF"
    CONTENT_EQUIVALENT = "CONTENT_EQUIVALENT"


class EvidenceValidationError(ValueError):
    """Raised before persistence when an evidence submission is invalid."""


class EvidenceIdentityConflict(EvidenceValidationError):
    """Raised when one source claims two conflicting source-item identities."""


_TRACKING_PARAMETER_NAMES = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
}


def canonicalize_url(url: str) -> str:
    """Normalize a source URL without removing meaningful application parameters."""

    if not isinstance(url, str) or not url.strip():
        raise EvidenceValidationError("canonical_url is required")
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise EvidenceValidationError("canonical_url must be an HTTP(S) URL")
    if parsed.username or parsed.password:
        raise EvidenceValidationError("canonical_url must not contain credentials")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise EvidenceValidationError("canonical_url must contain a host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise EvidenceValidationError("canonical_url contains an invalid port") from exc
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    host = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETER_NAMES
    ]
    query.sort()
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(query), ""))


def content_hash(raw_content: str | bytes | None) -> str:
    """Return a stable SHA-256 hash for inline content."""

    if raw_content is None:
        raise EvidenceValidationError("raw_content is required to calculate content_hash")
    payload = raw_content.encode("utf-8") if isinstance(raw_content, str) else raw_content
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    source_type: SourceType
    name: str
    canonical_root: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceSubmission:
    source_id: str
    canonical_url: str
    native_id: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = field(default_factory=utc_now)
    raw_content: str | None = None
    snapshot_ref: str | None = None
    supplied_content_hash: str | None = None
    retrieval_metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> "EvidenceSubmission":
        if not self.source_id.strip():
            raise EvidenceValidationError("source_id is required")
        normalized_url = canonicalize_url(self.canonical_url)
        if self.raw_content is None and not (self.snapshot_ref and self.snapshot_ref.strip()):
            raise EvidenceValidationError("provide raw_content or snapshot_ref")
        calculated_hash = content_hash(self.raw_content) if self.raw_content is not None else None
        if self.supplied_content_hash is not None:
            supplied = self.supplied_content_hash.strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", supplied):
                raise EvidenceValidationError("content_hash must be a SHA-256 hex digest")
            if calculated_hash is not None and calculated_hash != supplied:
                raise EvidenceValidationError("content_hash does not match raw_content")
            normalized_hash = supplied
        else:
            if calculated_hash is None:
                raise EvidenceValidationError(
                    "supplied_content_hash is required when raw_content is absent"
                )
            normalized_hash = calculated_hash
        retrieved_at = self.retrieved_at
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
        published_at = self.published_at
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        return EvidenceSubmission(
            source_id=self.source_id.strip(),
            canonical_url=normalized_url,
            native_id=self.native_id.strip() if self.native_id and self.native_id.strip() else None,
            title=self.title,
            published_at=published_at,
            retrieved_at=retrieved_at,
            raw_content=self.raw_content,
            snapshot_ref=self.snapshot_ref.strip() if self.snapshot_ref else None,
            supplied_content_hash=normalized_hash,
            retrieval_metadata=dict(self.retrieval_metadata),
        )


@dataclass(frozen=True, slots=True)
class IngestResult:
    evidence_id: str
    source_item_id: str
    retrieval_id: str
    created: bool
    version_of: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    source_item_id: str
    source_id: str
    source_type: SourceType
    source_name: str
    canonical_url: str
    native_id: str | None
    title: str | None
    content_hash: str
    retrieved_at: datetime
    published_at: datetime | None
    schema_version: int
    raw_content: str | None
    snapshot_ref: str | None
    previous_evidence_id: str | None


@dataclass(frozen=True, slots=True)
class ProvenanceEdge:
    edge_id: str
    relationship: ProvenanceRelationship
    from_id: str
    to_id: str
    created_at: datetime
