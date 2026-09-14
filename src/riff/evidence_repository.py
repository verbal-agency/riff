"""Postgres persistence operations for the G01 evidence store."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from .db import connection
from .evidence import (
    EvidenceRecord,
    EvidenceSubmission,
    EvidenceValidationError,
    IngestResult,
    ProvenanceEdge,
    ProvenanceRelationship,
    RetrievalOutcome,
    Source,
    SourceType,
)


SCHEMA_VERSION = 1


def _id() -> str:
    return str(uuid.uuid4())


def _as_text(value: Any) -> Any:
    """Normalize text values returned by text/binary psycopg cursors."""

    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return value


class EvidenceRepository:
    """Application repository with one transaction per mutating operation."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def create_source(
        self,
        source_type: SourceType,
        name: str,
        *,
        canonical_root: str | None = None,
        enabled: bool = True,
        source_id: str | None = None,
    ) -> Source:
        try:
            normalized_type = SourceType(source_type)
        except ValueError as exc:
            raise EvidenceValidationError(f"unknown source_type: {source_type}") from exc
        if not name.strip():
            raise EvidenceValidationError("source name is required")
        normalized_root = None
        if canonical_root:
            from .evidence import canonicalize_url

            normalized_root = canonicalize_url(canonical_root)
        source = Source(source_id=source_id or _id(), source_type=normalized_type, name=name.strip(), canonical_root=normalized_root, enabled=enabled)
        with connection(self.database_url) as conn:
            conn.execute(
                """
                INSERT INTO sources (source_id, source_type, name, canonical_root, enabled)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    name = EXCLUDED.name,
                    canonical_root = EXCLUDED.canonical_root,
                    enabled = EXCLUDED.enabled
                """,
                (source.source_id, source.source_type.value, source.name, source.canonical_root, source.enabled),
            )
        return source

    def ingest(self, submission: EvidenceSubmission) -> IngestResult:
        item = submission.validate()
        with connection(self.database_url) as conn:
            source = conn.execute(
                "SELECT source_id FROM sources WHERE source_id = %s",
                (item.source_id,),
            ).fetchone()
            if source is None:
                raise EvidenceValidationError(f"unknown source_id: {item.source_id}")

            by_native = None
            if item.native_id is not None:
                by_native = conn.execute(
                    "SELECT source_item_id, native_id, canonical_url FROM source_items "
                    "WHERE source_id = %s AND native_id = %s",
                    (item.source_id, item.native_id),
                ).fetchone()
            by_url = None
            if item.native_id is None:
                by_url = conn.execute(
                    "SELECT source_item_id, native_id, canonical_url FROM source_items "
                    "WHERE source_id = %s AND canonical_url = %s AND native_id IS NULL",
                    (item.source_id, item.canonical_url),
                ).fetchone()
                if by_url:
                    by_url = tuple(_as_text(value) for value in by_url)
            if by_native:
                by_native = tuple(_as_text(value) for value in by_native)
            existing = by_native or by_url
            if existing:
                source_item_id = existing[0]
                if existing[2] != item.canonical_url:
                    conn.execute(
                        "UPDATE source_items SET canonical_url = %s, title = COALESCE(%s, title) "
                        "WHERE source_item_id = %s",
                        (item.canonical_url, item.title, source_item_id),
                    )
                elif item.title is not None:
                    conn.execute(
                        "UPDATE source_items SET title = %s WHERE source_item_id = %s",
                        (item.title, source_item_id),
                    )
            else:
                proposed_source_item_id = _id()
                insert_item = conn.execute(
                    "INSERT INTO source_items "
                    "(source_item_id, source_id, native_id, canonical_url, title) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (proposed_source_item_id, item.source_id, item.native_id, item.canonical_url, item.title),
                )
                if insert_item.rowcount:
                    source_item_id = proposed_source_item_id
                else:
                    identity_column = "native_id" if item.native_id is not None else "canonical_url"
                    raced = conn.execute(
                        f"SELECT source_item_id FROM source_items WHERE source_id = %s AND {identity_column} = %s",
                        (item.source_id, item.native_id or item.canonical_url),
                    ).fetchone()
                    if raced is None:
                        raise EvidenceValidationError("source item could not be resolved after a concurrent write")
                    source_item_id = _as_text(raced[0])

            existing_evidence = conn.execute(
                "SELECT evidence_id FROM evidence_versions "
                "WHERE source_item_id = %s AND content_hash = %s",
                (source_item_id, item.supplied_content_hash),
            ).fetchone()
            if existing_evidence:
                existing_evidence = tuple(_as_text(value) for value in existing_evidence)
            if existing_evidence:
                evidence_id = existing_evidence[0]
                created = False
                version_of = None
            else:
                previous = conn.execute(
                    "SELECT evidence_id FROM evidence_versions "
                    "WHERE source_item_id = %s ORDER BY retrieved_at DESC LIMIT 1",
                    (source_item_id,),
                ).fetchone()
                if previous:
                    previous = tuple(_as_text(value) for value in previous)
                evidence_id = _id()
                version_of = previous[0] if previous else None
                insert_evidence = conn.execute(
                    """
                    INSERT INTO evidence_versions
                    (evidence_id, source_item_id, content_hash, retrieved_at, published_at,
                     raw_content, snapshot_ref, schema_version, previous_evidence_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        evidence_id,
                        source_item_id,
                        item.supplied_content_hash,
                        item.retrieved_at,
                        item.published_at,
                        item.raw_content,
                        item.snapshot_ref,
                        SCHEMA_VERSION,
                        version_of,
                    ),
                )
                if insert_evidence.rowcount and version_of:
                    self._insert_edge(
                        conn,
                        ProvenanceRelationship.VERSION_OF,
                        from_evidence_id=evidence_id,
                        to_evidence_id=version_of,
                    )
                if insert_evidence.rowcount:
                    created = True
                else:
                    raced_evidence = conn.execute(
                        "SELECT evidence_id FROM evidence_versions "
                        "WHERE source_item_id = %s AND content_hash = %s",
                        (source_item_id, item.supplied_content_hash),
                    ).fetchone()
                    if raced_evidence is None:
                        raise EvidenceValidationError("evidence could not be resolved after a concurrent write")
                    evidence_id = _as_text(raced_evidence[0])
                    version_of = None
                    created = False

            retrieval_id = _id()
            conn.execute(
                "INSERT INTO retrievals (retrieval_id, evidence_id, retrieved_at, outcome, metadata) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    retrieval_id,
                    evidence_id,
                    item.retrieved_at,
                    RetrievalOutcome.SUCCESS.value,
                    Jsonb(item.retrieval_metadata),
                ),
            )
            return IngestResult(evidence_id, source_item_id, retrieval_id, created, version_of)

    def get_evidence(self, evidence_id: str, *, include_raw: bool = False) -> EvidenceRecord | None:
        with connection(self.database_url) as conn:
            row = conn.execute(self._record_query("WHERE e.evidence_id = %s"), (evidence_id,)).fetchone()
        return self._record(row, include_raw=include_raw) if row else None

    def search(
        self,
        *,
        source_type: SourceType | None = None,
        source_id: str | None = None,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
        text: str | None = None,
        github_repository_id: str | None = None,
        github_organization: str | None = None,
        github_artifact_type: str | None = None,
        limit: int = 100,
    ) -> list[EvidenceRecord]:
        if limit < 1 or limit > 500:
            raise EvidenceValidationError("limit must be between 1 and 500")
        clauses: list[str] = []
        params: list[Any] = []
        joins = ""
        if source_type is not None:
            try:
                source_type = SourceType(source_type)
            except ValueError as exc:
                raise EvidenceValidationError(f"unknown source_type: {source_type}") from exc
            clauses.append("s.source_type = %s")
            params.append(source_type.value)
        if source_id:
            clauses.append("s.source_id = %s")
            params.append(source_id)
        if published_after is not None:
            clauses.append("e.published_at >= %s")
            params.append(published_after)
        if published_before is not None:
            clauses.append("e.published_at <= %s")
            params.append(published_before)
        if text:
            clauses.append("(e.raw_content ILIKE %s OR si.title ILIKE %s)")
            needle = f"%{text}%"
            params.extend([needle, needle])
        if github_repository_id or github_organization or github_artifact_type:
            joins = (
                " JOIN github_artifacts ga ON ga.evidence_id = e.evidence_id "
                " JOIN github_repositories gr ON gr.provider_repository_id = ga.provider_repository_id"
            )
        if github_repository_id:
            clauses.append("ga.provider_repository_id = %s")
            params.append(github_repository_id)
        if github_organization:
            clauses.append("gr.organization_login = %s")
            params.append(github_organization)
        if github_artifact_type:
            clauses.append("ga.artifact_type = %s")
            params.append(github_artifact_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = self._record_query(where, joins=joins) + " ORDER BY e.retrieved_at DESC LIMIT %s"
        params.append(limit)
        with connection(self.database_url) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._record(row, include_raw=False) for row in rows]

    def link_discovered_through(self, discovery_source_item_id: str, root_source_item_id: str) -> ProvenanceEdge:
        return self._link_source_items(
            ProvenanceRelationship.DISCOVERED_THROUGH,
            discovery_source_item_id,
            root_source_item_id,
        )

    def link_content_equivalent(self, source_item_id: str, equivalent_source_item_id: str) -> ProvenanceEdge:
        return self._link_source_items(
            ProvenanceRelationship.CONTENT_EQUIVALENT,
            source_item_id,
            equivalent_source_item_id,
        )

    def list_provenance(
        self, *, source_item_id: str | None = None, evidence_id: str | None = None
    ) -> list[ProvenanceEdge]:
        if not source_item_id and not evidence_id:
            raise EvidenceValidationError("source_item_id or evidence_id is required")
        clauses: list[str] = []
        params: list[str] = []
        if source_item_id:
            clauses.append(
                "(from_source_item_id = %s OR to_source_item_id = %s)"
            )
            params.extend([source_item_id, source_item_id])
        if evidence_id:
            clauses.append("(from_evidence_id = %s OR to_evidence_id = %s)")
            params.extend([evidence_id, evidence_id])
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT edge_id, relationship, from_source_item_id, to_source_item_id, "
                "from_evidence_id, to_evidence_id, created_at FROM provenance_edges "
                f"WHERE {' OR '.join(clauses)} ORDER BY created_at",
                params,
            ).fetchall()
        return [
            ProvenanceEdge(
                edge_id=row[0],
                relationship=ProvenanceRelationship(_as_text(row[1])),
                from_id=_as_text(row[2] or row[4]),
                to_id=_as_text(row[3] or row[5]),
                created_at=row[6],
            )
            for row in rows
        ]

    def source_item_count(self, source_id: str) -> int:
        with connection(self.database_url) as conn:
            row = conn.execute(
                "SELECT count(*) FROM source_items WHERE source_id = %s", (source_id,)
            ).fetchone()
        return int(row[0])

    @staticmethod
    def _record_query(where: str, *, joins: str = "") -> str:
        return (
            "SELECT e.evidence_id, e.source_item_id, s.source_id, s.source_type, s.name, "
            "si.canonical_url, si.native_id, si.title, e.content_hash, e.retrieved_at, "
            "e.published_at, e.schema_version, e.raw_content, e.snapshot_ref, "
            "e.previous_evidence_id FROM evidence_versions e "
            "JOIN source_items si ON si.source_item_id = e.source_item_id "
            "JOIN sources s ON s.source_id = si.source_id "
            f"{joins} "
            f"{where}"
        )

    @staticmethod
    def _record(row: tuple[Any, ...], *, include_raw: bool) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=_as_text(row[0]),
            source_item_id=_as_text(row[1]),
            source_id=_as_text(row[2]),
            source_type=SourceType(_as_text(row[3])),
            source_name=_as_text(row[4]),
            canonical_url=_as_text(row[5]),
            native_id=_as_text(row[6]),
            title=_as_text(row[7]),
            content_hash=_as_text(row[8]),
            retrieved_at=row[9],
            published_at=row[10],
            schema_version=row[11],
            raw_content=_as_text(row[12]) if include_raw else None,
            snapshot_ref=_as_text(row[13]),
            previous_evidence_id=_as_text(row[14]),
        )

    def _link_source_items(
        self,
        relationship: ProvenanceRelationship,
        from_source_item_id: str,
        to_source_item_id: str,
    ) -> ProvenanceEdge:
        if from_source_item_id == to_source_item_id:
            raise EvidenceValidationError("a provenance edge cannot point to itself")
        with connection(self.database_url) as conn:
            edge_id = self._insert_edge(
                conn,
                relationship,
                from_source_item_id=from_source_item_id,
                to_source_item_id=to_source_item_id,
            )
            row = conn.execute(
                "SELECT created_at FROM provenance_edges WHERE edge_id = %s", (edge_id,)
            ).fetchone()
        return ProvenanceEdge(_as_text(edge_id), relationship, from_source_item_id, to_source_item_id, row[0])

    @staticmethod
    def _insert_edge(
        conn,
        relationship: ProvenanceRelationship,
        *,
        from_source_item_id: str | None = None,
        to_source_item_id: str | None = None,
        from_evidence_id: str | None = None,
        to_evidence_id: str | None = None,
    ) -> str:
        edge_id = _id()
        conn.execute(
            "INSERT INTO provenance_edges "
            "(edge_id, relationship, from_source_item_id, to_source_item_id, "
            "from_evidence_id, to_evidence_id) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (
                edge_id,
                relationship.value,
                from_source_item_id,
                to_source_item_id,
                from_evidence_id,
                to_evidence_id,
            ),
        )
        row = conn.execute(
            "SELECT edge_id FROM provenance_edges WHERE relationship = %s AND "
            "from_source_item_id IS NOT DISTINCT FROM %s AND "
            "to_source_item_id IS NOT DISTINCT FROM %s AND "
            "from_evidence_id IS NOT DISTINCT FROM %s AND "
            "to_evidence_id IS NOT DISTINCT FROM %s",
            (
                relationship.value,
                from_source_item_id,
                to_source_item_id,
                from_evidence_id,
                to_evidence_id,
            ),
        ).fetchone()
        return _as_text(row[0])
