"""Postgres persistence for source configuration, cursors, and collection runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import EvidenceValidationError, SourceType


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ItemOutcome(str, Enum):
    STORED = "STORED"
    DUPLICATE = "DUPLICATE"
    SKIPPED = "SKIPPED"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"


@dataclass(frozen=True, slots=True)
class IngestionSource:
    source_id: str
    source_type: SourceType
    name: str
    endpoint: str
    enabled: bool
    config_version: int
    cursor_kind: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class CollectionRun:
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    source_ids: list[str]
    policy_version: str


@dataclass(frozen=True, slots=True)
class ItemResult:
    run_id: str
    source_id: str
    outcome: str
    canonical_url: str | None
    source_native_id: str | None
    evidence_id: str | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    run_id: str
    status: str
    stored: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed_transient: int = 0
    failed_permanent: int = 0


def _id() -> str:
    return str(uuid.uuid4())


def _text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value


class IngestionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def configure_source(
        self,
        source_id: str,
        endpoint: str,
        *,
        enabled: bool = True,
        config_version: int = 1,
        cursor_kind: str = "updated_at",
        metadata: Mapping[str, object] | None = None,
    ) -> IngestionSource:
        if not endpoint.strip().lower().startswith(("http://", "https://")):
            raise EvidenceValidationError("endpoint must be an HTTP(S) URL")
        if config_version < 1 or not cursor_kind.strip():
            raise EvidenceValidationError("config_version and cursor_kind are required")
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT source_type, name FROM sources WHERE source_id = %s", (source_id,)
            ).fetchone()
            if row is None:
                raise EvidenceValidationError(f"unknown source_id: {source_id}")
            source_type, name = SourceType(_text(row[0])), _text(row[1])
            conn.execute(
                """
                INSERT INTO ingestion_source_configs
                (source_id, endpoint, enabled, config_version, cursor_kind, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    endpoint = EXCLUDED.endpoint,
                    enabled = EXCLUDED.enabled,
                    config_version = EXCLUDED.config_version,
                    cursor_kind = EXCLUDED.cursor_kind,
                    metadata = EXCLUDED.metadata
                """,
                (source_id, endpoint.strip(), enabled, config_version, cursor_kind.strip(), Jsonb(dict(metadata or {}))),
            )
            conn.execute("UPDATE sources SET enabled = %s WHERE source_id = %s", (enabled, source_id))
        return IngestionSource(source_id, source_type, name, endpoint.strip(), enabled, config_version, cursor_kind.strip(), dict(metadata or {}))

    def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        with connection(self.database_url) as conn:
            result = conn.execute("UPDATE sources SET enabled = %s WHERE source_id = %s", (enabled, source_id))
            if result.rowcount == 0:
                raise EvidenceValidationError(f"unknown source_id: {source_id}")
            conn.execute("UPDATE ingestion_source_configs SET enabled = %s WHERE source_id = %s", (enabled, source_id))

    def list_sources(
        self,
        *,
        source_ids: Iterable[str] | None = None,
        source_type: SourceType | None = None,
    ) -> list[IngestionSource]:
        clauses = ["s.source_id = c.source_id"]
        params: list[Any] = []
        if source_ids:
            ids = list(source_ids)
            clauses.append("s.source_id = ANY(%s)")
            params.append(ids)
        if source_type is not None:
            try:
                source_type = SourceType(source_type)
            except ValueError as exc:
                raise EvidenceValidationError(f"unknown source_type: {source_type}") from exc
            clauses.append("s.source_type = %s")
            params.append(source_type.value)
        query = (
            "SELECT s.source_id, s.source_type, s.name, c.endpoint, c.enabled, "
            "c.config_version, c.cursor_kind, c.metadata FROM sources s JOIN ingestion_source_configs c "
            f"ON {' AND '.join(clauses)} ORDER BY s.name"
        )
        with connection(self.database_url) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            IngestionSource(
                source_id=_text(row[0]),
                source_type=SourceType(_text(row[1])),
                name=_text(row[2]),
                endpoint=_text(row[3]),
                enabled=bool(row[4]),
                config_version=int(row[5]),
                cursor_kind=_text(row[6]),
                metadata=dict(row[7] or {}),
            )
            for row in rows
        ]

    def get_cursor(self, source_id: str, cursor_kind: str) -> str | None:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT cursor_value FROM collection_cursors WHERE source_id = %s AND cursor_kind = %s",
                (source_id, cursor_kind),
            ).fetchone()
        return _text(row[0]) if row else None

    def update_cursor(self, source_id: str, cursor_kind: str, cursor_value: str) -> None:
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO collection_cursors (source_id, cursor_kind, cursor_value)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_id, cursor_kind) DO UPDATE SET
                    cursor_value = EXCLUDED.cursor_value,
                    updated_at = now()
                """,
                (source_id, cursor_kind, cursor_value),
            )

    def start_run(self, source_ids: list[str], policy_version: str) -> CollectionRun:
        run_id = _id()
        started_at = datetime.now(timezone.utc)
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO collection_runs "
                "(run_id, started_at, status, source_ids, policy_version) VALUES (%s, %s, %s, %s, %s)",
                (run_id, started_at, RunStatus.RUNNING, Jsonb(source_ids), policy_version),
            )
        return CollectionRun(run_id, RunStatus.RUNNING, started_at, None, source_ids, policy_version)

    def finish_run(self, run_id: str, status: str, *, finished_at: datetime | None = None) -> None:
        if status not in {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED}:
            raise EvidenceValidationError(f"invalid terminal run status: {status}")
        with connection(self.database_url) as conn:
            result = conn.execute(
                "UPDATE collection_runs SET status = %s, finished_at = %s "
                "WHERE run_id = %s AND status = %s",
                (status, finished_at or datetime.now(timezone.utc), run_id, RunStatus.RUNNING),
            )
            if result.rowcount != 1:
                raise EvidenceValidationError("collection run is missing or already finished")

    def record_item_result(
        self,
        run_id: str,
        source_id: str,
        outcome: str,
        *,
        canonical_url: str | None = None,
        source_native_id: str | None = None,
        evidence_id: str | None = None,
        error_code: str | None = None,
    ) -> ItemResult:
        if outcome not in {
            ItemOutcome.STORED,
            ItemOutcome.DUPLICATE,
            ItemOutcome.SKIPPED,
            ItemOutcome.FAILED_TRANSIENT,
            ItemOutcome.FAILED_PERMANENT,
        }:
            raise EvidenceValidationError(f"invalid item outcome: {outcome}")
        if outcome in {ItemOutcome.STORED, ItemOutcome.DUPLICATE} and not evidence_id:
            raise EvidenceValidationError("stored/duplicate item results require evidence_id")
        if outcome in {ItemOutcome.FAILED_TRANSIENT, ItemOutcome.FAILED_PERMANENT} and evidence_id:
            raise EvidenceValidationError("failed item results cannot contain evidence_id")
        with connection(self.database_url) as conn:
            conn.execute(
                "INSERT INTO collection_item_results "
                "(run_id, source_id, canonical_url, source_native_id, outcome, evidence_id, error_code) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (run_id, source_id, canonical_url, source_native_id, outcome, evidence_id, error_code),
            )
        return ItemResult(run_id, source_id, outcome, canonical_url, source_native_id, evidence_id, error_code)
