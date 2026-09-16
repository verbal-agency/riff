"""Deterministic provenance-quality and epistemic-confidence policy.

Candidate relevance is intentionally kept separate from evidence quality.  The
policy is pure so it can be exercised offline and replayed when a policy or
receipt changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection


POLICY_VERSION = "provenance-policy-v1"
MAX_EPISTEMIC_CONFIDENCE = 0.95


def derive_stale_run_status(outcomes: Sequence[str]) -> tuple[str, str]:
    """Return a terminal status/reason without guessing about missing work."""

    if not outcomes:
        return "FAILED", "STALE_RUN_NO_ITEM_RESULTS"
    if any(item in {"FAILED_TRANSIENT", "FAILED_PERMANENT"} for item in outcomes):
        return "PARTIAL", "STALE_RUN_WITH_FAILURES"
    return "SUCCEEDED", "STALE_RUN_RECONCILED"


def backfill_receipt_metadata(database_url: str) -> dict[str, int]:
    """Fill only absent receipt provenance fields from canonical source rows."""

    with connection(database_url) as conn:
        before = conn.execute(
            """SELECT count(*) FILTER (WHERE r.source_metadata->>'source_type' IS NULL),
                              count(*) FILTER (WHERE r.source_metadata->>'source_id' IS NULL),
                              count(*) FILTER (WHERE r.source_metadata->>'evidence_id' IS NULL)
               FROM evidence_receipts r"""
        ).fetchone()
        updated = conn.execute(
            """UPDATE evidence_receipts r
               SET source_metadata = r.source_metadata || jsonb_strip_nulls(jsonb_build_object(
                   'evidence_id', COALESCE(r.source_metadata->>'evidence_id', r.evidence_id),
                   'source_id', COALESCE(r.source_metadata->>'source_id', s.source_id),
                   'source_type', COALESCE(r.source_metadata->>'source_type', s.source_type),
                   'source_name', COALESCE(r.source_metadata->>'source_name', s.name),
                   'canonical_root', COALESCE(r.source_metadata->>'canonical_root', s.canonical_root),
                   'person_name', COALESCE(r.source_metadata->>'person_name', c.metadata->>'person_name'),
                   'organization_at_publication', COALESCE(r.source_metadata->>'organization_at_publication', c.metadata->>'organization_at_publication'),
                   'correlation_group', COALESCE(r.source_metadata->>'correlation_group', c.metadata->>'correlation_group'),
                   'source_root', COALESCE(r.source_metadata->>'source_root', c.metadata->>'source_root')
               ))
               FROM evidence_versions e
               JOIN source_items si ON si.source_item_id = e.source_item_id
               JOIN sources s ON s.source_id = si.source_id
               LEFT JOIN ingestion_source_configs c ON c.source_id = s.source_id
               WHERE r.evidence_id = e.evidence_id
                 AND (r.source_metadata->>'source_type' IS NULL
                   OR r.source_metadata->>'source_id' IS NULL
                   OR r.source_metadata->>'evidence_id' IS NULL
                   OR r.source_metadata->>'source_name' IS NULL
                   OR (c.metadata ? 'person_name' AND r.source_metadata->>'person_name' IS NULL)
                   OR (c.metadata ? 'organization_at_publication' AND r.source_metadata->>'organization_at_publication' IS NULL)
                   OR (c.metadata ? 'correlation_group' AND r.source_metadata->>'correlation_group' IS NULL))"""
        )
        after = conn.execute(
            """SELECT count(*) FILTER (WHERE r.source_metadata->>'source_type' IS NULL),
                              count(*) FILTER (WHERE r.source_metadata->>'source_id' IS NULL),
                              count(*) FILTER (WHERE r.source_metadata->>'evidence_id' IS NULL)
               FROM evidence_receipts r"""
        ).fetchone()
    return {
        "rows_updated": int(updated.rowcount),
        "missing_source_type_before": int(before[0]),
        "missing_source_type_after": int(after[0]),
        "missing_source_id_before": int(before[1]),
        "missing_source_id_after": int(after[1]),
        "missing_evidence_id_before": int(before[2]),
        "missing_evidence_id_after": int(after[2]),
    }


def reconcile_stale_collection_runs(database_url: str, *, stale_after: timedelta = timedelta(hours=1)) -> dict[str, Any]:
    """Close stale collection runs using only their recorded item outcomes."""

    cutoff = datetime.now(timezone.utc) - stale_after
    changed: list[dict[str, str]] = []
    with connection(database_url) as conn:
        rows = conn.execute(
            "SELECT run_id FROM collection_runs WHERE status = 'RUNNING' AND started_at < %s FOR UPDATE",
            (cutoff,),
        ).fetchall()
        for (run_id_raw,) in rows:
            run_id = str(run_id_raw)
            outcomes = [str(item[0]) for item in conn.execute("SELECT outcome FROM collection_item_results WHERE run_id = %s ORDER BY created_at", (run_id,)).fetchall()]
            status, reason = derive_stale_run_status(outcomes)
            conn.execute("UPDATE collection_runs SET status = %s, finished_at = now(), completion_reason = %s WHERE run_id = %s AND status = 'RUNNING'", (status, reason, run_id))
            changed.append({"run_id": run_id, "status": status, "reason": reason})
    return {"stale_after_seconds": int(stale_after.total_seconds()), "reconciled": len(changed), "runs": changed}


def source_coverage_report(database_url: str, *, limit: int = 100, include_non_live: bool = False) -> dict[str, Any]:
    """Return bounded, aggregate coverage for configured sources."""

    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    with connection(database_url) as conn:
        rows = conn.execute(
            """WITH evidence_counts AS (
                   SELECT si.source_id,
                          count(DISTINCT e.evidence_id) AS evidence_count,
                          count(DISTINCT e.evidence_id) FILTER (WHERE r.source_metadata->>'fixture' = 'true') AS fixture_count
                   FROM source_items si
                   JOIN evidence_versions e ON e.source_item_id = si.source_item_id
                   LEFT JOIN evidence_receipts r ON r.evidence_id = e.evidence_id
                   WHERE (%s OR COALESCE(e.data_origin, 'UNCLASSIFIED') NOT IN ('FIXTURE', 'TEST', 'QUARANTINED'))
                   GROUP BY si.source_id
               ), run_counts AS (
                   SELECT source_id.value AS source_id,
                          count(*) AS collection_runs,
                          count(*) FILTER (WHERE cr.status = 'FAILED') AS failed_runs,
                          max(cr.started_at) AS last_started
                   FROM collection_runs cr
                   CROSS JOIN LATERAL jsonb_array_elements_text(cr.source_ids) AS source_id(value)
                   GROUP BY source_id.value
               )
               SELECT s.source_id, s.source_type, s.enabled,
                      COALESCE(e.evidence_count, 0), COALESCE(e.fixture_count, 0),
                      COALESCE(rc.collection_runs, 0), COALESCE(rc.failed_runs, 0), rc.last_started
               FROM sources s
               LEFT JOIN evidence_counts e ON e.source_id = s.source_id
               LEFT JOIN run_counts rc ON rc.source_id = s.source_id
               WHERE (%s OR COALESCE(s.data_origin, 'UNCLASSIFIED') NOT IN ('FIXTURE', 'TEST', 'QUARANTINED'))
               ORDER BY COALESCE(e.evidence_count, 0), s.source_id""",
            (include_non_live, include_non_live),
        ).fetchall()
    items = []
    for row in rows:
        evidence_count, fixture_count, run_count, failed_runs = map(int, row[3:7])
        if evidence_count == 0 and run_count == 0:
            state = "NEVER_COLLECTED"
        elif evidence_count == 0 and failed_runs:
            state = "FAILED"
        elif evidence_count == 0:
            state = "EMPTY"
        elif fixture_count == evidence_count:
            state = "FIXTURE_ONLY"
        else:
            state = "COLLECTED"
        items.append({"source_id": str(row[0]), "source_type": str(row[1]), "enabled": bool(row[2]), "evidence_count": evidence_count, "fixture_evidence_count": fixture_count, "collection_runs": run_count, "failed_runs": failed_runs, "last_started": row[7].isoformat() if row[7] else None, "state": state})
    counts: dict[str, int] = {}
    for item in items:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    return {"limit": limit, "total": len(items), "returned": min(limit, len(items)), "states": counts, "sources": items[:limit]}


def engineer_source_coverage_report(database_url: str, *, limit: int = 100, include_non_live: bool = False) -> dict[str, Any]:
    """Report engineer-attributed source coverage without inferring identity.

    Rows are grouped by the explicit ``engineer_source_id`` carried in the
    ingestion source configuration.  Evidence counts come from persisted
    evidence/retrieval rows, so fixture-only coverage cannot masquerade as live
    provenance.
    """

    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    with connection(database_url) as conn:
        rows = conn.execute(
            """WITH run_counts AS (
                   SELECT source_id.value AS source_id,
                          count(*) AS collection_runs,
                          count(*) FILTER (WHERE cr.status = 'FAILED') AS failed_runs
                   FROM collection_runs cr
                   CROSS JOIN LATERAL jsonb_array_elements_text(cr.source_ids) AS source_id(value)
                   GROUP BY source_id.value
               ), source_counts AS (
                   SELECT isc.source_id,
                          isc.metadata->>'engineer_source_id' AS engineer_source_id,
                          isc.metadata->>'person_id' AS person_id,
                          isc.metadata->>'person_name' AS person_name,
                          isc.metadata->>'organization_at_publication' AS organization_at_publication,
                          isc.metadata->>'source_root' AS source_root,
                          isc.metadata->>'correlation_group' AS correlation_group,
                          s.enabled,
                          count(DISTINCT e.evidence_id) AS evidence_count,
                          count(DISTINCT e.evidence_id) FILTER (WHERE r.metadata->>'fixture' = 'true') AS fixture_evidence_count,
                          count(DISTINCT e.evidence_id) FILTER (WHERE COALESCE(r.metadata->>'fixture', 'false') <> 'true') AS non_fixture_evidence_count,
                          COALESCE(rc.collection_runs, 0) AS collection_runs,
                          COALESCE(rc.failed_runs, 0) AS failed_runs
                   FROM ingestion_source_configs isc
                   JOIN sources s ON s.source_id = isc.source_id
                   LEFT JOIN source_items si ON si.source_id = isc.source_id
                   LEFT JOIN evidence_versions e ON e.source_item_id = si.source_item_id
                   LEFT JOIN retrievals r ON r.evidence_id = e.evidence_id
                   LEFT JOIN run_counts rc ON rc.source_id = isc.source_id
                   WHERE isc.metadata ? 'engineer_source_id'
                     AND (%s OR COALESCE(s.data_origin, 'UNCLASSIFIED') NOT IN ('FIXTURE', 'TEST', 'QUARANTINED'))
                   GROUP BY isc.source_id, isc.metadata, s.enabled, rc.collection_runs, rc.failed_runs
               )
               SELECT engineer_source_id,
                      min(person_id), min(person_name), min(organization_at_publication),
                      min(source_root), min(correlation_group),
                      count(*) AS source_count,
                      count(*) FILTER (WHERE enabled) AS enabled_source_count,
                      array_agg(source_id ORDER BY source_id) AS source_ids,
                      sum(evidence_count), sum(fixture_evidence_count),
                      sum(non_fixture_evidence_count), sum(collection_runs), sum(failed_runs),
                      jsonb_object_agg(source_id, jsonb_build_object(
                          'enabled', enabled,
                          'evidence_count', evidence_count,
                          'fixture_evidence_count', fixture_evidence_count,
                          'non_fixture_evidence_count', non_fixture_evidence_count,
                          'collection_runs', collection_runs,
                          'failed_runs', failed_runs
                      )) AS sources
               FROM source_counts
               GROUP BY engineer_source_id
               ORDER BY engineer_source_id""",
            (include_non_live,),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        evidence_count = int(row[9] or 0)
        fixture_count = int(row[10] or 0)
        non_fixture_count = int(row[11] or 0)
        collection_runs = int(row[12] or 0)
        failed_runs = int(row[13] or 0)
        if evidence_count == 0 and collection_runs == 0:
            state = "NEVER_COLLECTED"
        elif evidence_count == 0 and failed_runs:
            state = "FAILED"
        elif evidence_count == 0:
            state = "EMPTY"
        elif non_fixture_count == 0:
            state = "FIXTURE_ONLY"
        else:
            state = "COLLECTED"
        items.append(
            {
                "engineer_source_id": str(row[0]),
                "person_id": row[1],
                "person_name": row[2],
                "organization_at_publication": row[3],
                "source_root": row[4],
                "correlation_group": row[5],
                "source_count": int(row[6]),
                "enabled_source_count": int(row[7]),
                "source_ids": [str(value) for value in (row[8] or [])],
                "evidence_count": evidence_count,
                "fixture_evidence_count": fixture_count,
                "non_fixture_evidence_count": non_fixture_count,
                "collection_runs": collection_runs,
                "failed_runs": failed_runs,
                "state": state,
                "sources": row[14] or {},
            }
        )
    states: dict[str, int] = {}
    for item in items:
        states[item["state"]] = states.get(item["state"], 0) + 1
    return {
        "limit": limit,
        "total": len(items),
        "returned": min(limit, len(items)),
        "states": states,
        "engineer_sources": items[:limit],
    }


def recalibrate_riffs(database_url: str, *, force: bool = False) -> dict[str, Any]:
    """Persist current provenance summaries without changing decisions/statuses."""

    from .decisions import DecisionRepository

    with connection(database_url) as conn:
        riff_ids = [str(row[0]) for row in conn.execute("SELECT riff_id FROM riffs ORDER BY created_at").fetchall()]
    changed: list[str] = []
    skipped = 0
    repository = DecisionRepository(database_url)
    for riff_id in riff_ids:
        investigation = repository.investigation(riff_id)
        quality = investigation.provenance_quality
        with connection(database_url) as conn:
            current = conn.execute("SELECT confidence_policy_version, provenance_summary FROM riffs WHERE riff_id = %s", (riff_id,)).fetchone()
            summary = current[1] if current else None
            has_interpretation = isinstance(summary, dict) and isinstance(summary.get("summary"), dict) and "interpretation" in summary["summary"]
            if not force and current and current[0] == POLICY_VERSION and has_interpretation:
                skipped += 1
                continue
            conn.execute(
                "UPDATE riffs SET evidence_quality = %s, epistemic_confidence = %s, confidence_policy_version = %s, provenance_summary = %s WHERE riff_id = %s",
                (quality["evidence_quality"], quality["epistemic_confidence"], quality["policy_version"], Jsonb(quality), riff_id),
            )
        changed.append(riff_id)
    return {"riffs_seen": len(riff_ids), "recalibrated": len(changed), "skipped_current": skipped, "riff_ids": changed, "policy_version": POLICY_VERSION}


@dataclass(frozen=True, slots=True)
class ProvenanceQuality:
    evidence_quality: float
    epistemic_confidence: float
    state: str
    promotion_allowed: bool
    summary: dict[str, Any]
    limitations: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_quality": self.evidence_quality,
            "epistemic_confidence": self.epistemic_confidence,
            "state": self.state,
            "promotion_allowed": self.promotion_allowed,
            "policy_version": self.policy_version,
            "summary": self.summary,
            "limitations": list(self.limitations),
        }


def assess_provenance(
    supporting: Sequence[Mapping[str, Any]],
    counterevidence: Sequence[Mapping[str, Any]] = (),
    *,
    candidate_score: float | None = None,
    generated_confidence: float | None = None,
    policy_version: str = POLICY_VERSION,
) -> ProvenanceQuality:
    """Assess support without treating receipt volume as independence.

    Inputs are bounded receipt projections, not arbitrary corpus rows.  Missing
    metadata remains unknown and is surfaced in ``limitations``.
    """

    support = [_normalize(item) for item in supporting]
    counter = [_normalize(item) for item in counterevidence]
    all_items = support + counter
    fixture_count = sum(1 for item in support if item["fixture"])
    roots = {item["independence_key"] for item in support if item["independence_key"]}
    source_types = {item["source_type"] for item in support if item["source_type"]}
    organizations = {item["organization"] for item in support if item["organization"]}
    authors = {item["author"] for item in support if item["author"]}
    content_hashes = [item["content_hash"] for item in support if item["content_hash"]]
    duplicate_content = len(content_hashes) - len(set(content_hashes))
    repost_count = sum(1 for item in support if item["repost"])
    citation_complete = sum(1 for item in support if item["citation_complete"])

    missing: list[str] = []
    for label, values in (("root source", roots), ("author", authors), ("organization", organizations)):
        if support and not values:
            missing.append(f"unknown {label} coverage")
    if support and citation_complete < len(support):
        missing.append(f"{len(support) - citation_complete} receipt(s) have incomplete citation metadata")

    if not support:
        state = "INSUFFICIENT"
        quality = 0.0
    elif fixture_count == len(support):
        state = "FIXTURE_ONLY"
        quality = 0.05
        missing.append("all supporting receipts are synthetic fixtures, not production evidence")
    elif counter:
        state = "CONTRADICTORY"
        quality = 0.35
    elif len(roots) < 2:
        state = "SINGLE_SOURCE"
        quality = 0.35
    else:
        state = "SUPPORTED"
        quality = 0.55 + min(0.20, (len(roots) - 2) * 0.05)
        quality += min(0.10, max(0, len(source_types) - 1) * 0.05)
        quality += min(0.10, max(0, len(organizations) - 1) * 0.05)
        quality += min(0.05, max(0, len(authors) - 1) * 0.025)
        if len(support) and citation_complete == len(support):
            quality += 0.05
    if duplicate_content or repost_count:
        quality = max(0.0, quality - min(0.20, 0.10 * max(duplicate_content, repost_count)))
        missing.append("reposts or duplicate content are downweighted")
    if counter:
        missing.append("counterevidence is present; the claim needs resolution before promotion")
    quality = round(min(1.0, quality), 4)

    ceiling = {
        "FIXTURE_ONLY": 0.20,
        "SINGLE_SOURCE": 0.55,
        "CONTRADICTORY": 0.45,
        "INSUFFICIENT": 0.20,
    }.get(state, MAX_EPISTEMIC_CONFIDENCE)
    raw_confidence = generated_confidence if generated_confidence is not None else candidate_score
    if raw_confidence is None:
        raw_confidence = 0.0
    epistemic = round(min(float(raw_confidence), quality, ceiling), 4)
    promotion_allowed = state == "SUPPORTED" and quality >= 0.70 and not counter and not missing
    summary = {
        "supporting_receipt_count": len(support),
        "counterevidence_count": len(counter),
        "fixture_receipt_count": fixture_count,
        "independent_root_count": len(roots),
        "source_type_count": len(source_types),
        "organization_count": len(organizations),
        "author_count": len(authors),
        "duplicate_content_count": duplicate_content,
        "repost_count": repost_count,
        "citation_complete_count": citation_complete,
        "observed_source_types": sorted(source_types),
        "observed_roots": sorted(roots),
        "unknown_provenance_fields": sorted(set(missing)),
        "evidence_quality": quality,
        "epistemic_confidence_ceiling": ceiling,
    }
    if state == "FIXTURE_ONLY":
        summary["interpretation"] = "Interesting hypothesis, but not supported by production evidence; do not promote on this evidence alone."
    elif state == "SINGLE_SOURCE":
        summary["interpretation"] = "Worth investigating, but one provenance root is insufficient for an established claim."
    elif state == "CONTRADICTORY":
        summary["interpretation"] = "Interesting but disputed; resolve counterevidence before promotion."
    elif state == "SUPPORTED":
        summary["interpretation"] = "Evidence is converging across independent provenance roots."
    else:
        summary["interpretation"] = "Insufficient provenance to assess the claim."
    return ProvenanceQuality(quality, epistemic, state, promotion_allowed, summary, tuple(sorted(set(missing))), policy_version)


def _normalize(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("source_metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    url = str(item.get("canonical_url") or "").strip()
    parsed = urlsplit(url) if url else None
    host = (parsed.hostname or "").lower() if parsed else ""
    fixture = bool(metadata.get("fixture") or metadata.get("synthetic") or host == "fixture.riff.local")
    root = _first(metadata, "canonical_root", "source_root", "root_source", "correlation_group")
    if not root:
        root = f"host:{host}" if host else _first(metadata, "source_id")
    organization = _first(metadata, "organization", "organization_at_publication", "company", "company_name", "employer")
    author = _first(metadata, "author", "author_name", "person_name")
    source_type = _first(metadata, "source_type")
    content_hash = _first(item, "content_hash") or _first(metadata, "content_hash")
    repost = bool(metadata.get("repost") or metadata.get("syndicated") or metadata.get("content_equivalent"))
    return {
        "fixture": fixture,
        "independence_key": str(root).strip() if root else None,
        "source_type": str(source_type).strip() if source_type else None,
        "organization": str(organization).strip().lower() if organization else None,
        "author": str(author).strip().lower() if author else None,
        "content_hash": str(content_hash).strip().lower() if content_hash else None,
        "repost": repost,
        "citation_complete": bool(url and item.get("title") and source_type),
    }


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return value
    return None
