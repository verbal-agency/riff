"""Origin-aware cleanup, quarantine, and retention controls (G35)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .ingestion_repository import resolve_collection_origin

ORIGINS = {"LIVE", "FIXTURE", "TEST", "QUARANTINED", "UNCLASSIFIED"}
NON_LIVE = {"FIXTURE", "TEST", "QUARANTINED"}


class GovernanceError(ValueError):
    """A governance selector, transition, or dependency check is invalid."""


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode()
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except (TypeError, ValueError):
            return default
    return value if value is not None else default


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _audit(conn, operation: str, status: str, selector: Mapping[str, Any], plan: Mapping[str, Any], *, policy_version: str) -> str:
    audit_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO data_governance_audits (audit_id,operation,status,selector,plan,input_fingerprint,policy_version,applied_at) VALUES (%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='APPLIED' THEN now() ELSE NULL END)",
        (audit_id, operation, status, Jsonb(dict(selector)), Jsonb(dict(plan)), _fingerprint({"operation": operation, "selector": selector, "plan": plan}), policy_version, status),
    )
    return audit_id


def backfill_known_fixtures(database_url: str, *, owner: str = "legacy-project-fixture", policy_version: str = "governance-v1") -> dict[str, int]:
    """Classify only the known synthetic G26/G27 projections."""

    if not owner.strip():
        raise GovernanceError("owner is required")
    with connection(database_url) as conn:
        source = conn.execute("UPDATE sources SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s WHERE source_id='riff-daily-fixture-source' AND COALESCE(data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", ("daily-fixture", policy_version))
        items = conn.execute("UPDATE source_items SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s WHERE source_id='riff-daily-fixture-source' AND COALESCE(data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", ("daily-fixture", policy_version))
        evidence = conn.execute("UPDATE evidence_versions e SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s FROM source_items si WHERE si.source_item_id=e.source_item_id AND si.source_id='riff-daily-fixture-source' AND COALESCE(e.data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", ("daily-fixture", policy_version))
        retrievals = conn.execute("UPDATE retrievals r SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s FROM evidence_versions e WHERE e.evidence_id=r.evidence_id AND e.data_origin='FIXTURE' AND COALESCE(r.data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", ("daily-fixture", policy_version))
        projects = conn.execute("UPDATE github_project_inventory SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s WHERE (project_id LIKE 'g26-%%' OR project_id LIKE 'g27-%%') AND COALESCE(data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", (owner, policy_version))
        snapshots = conn.execute("UPDATE github_project_snapshots s SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s FROM github_project_inventory i WHERE i.project_id=s.project_id AND i.data_origin='FIXTURE' AND COALESCE(s.data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", (owner, policy_version))
        recommendations = conn.execute("UPDATE project_recommendations r SET data_origin='FIXTURE',origin_owner=%s,origin_policy_version=%s WHERE r.project_id IN (SELECT project_id FROM github_project_inventory WHERE data_origin='FIXTURE') AND COALESCE(r.data_origin,'UNCLASSIFIED')='UNCLASSIFIED'", (owner, policy_version))
        _audit(conn, "BACKFILL", "APPLIED", {"owner": owner, "known_prefixes": ["g26-", "g27-"], "daily_fixture_source": True}, {"source": source.rowcount, "source_items": items.rowcount, "evidence": evidence.rowcount, "retrievals": retrievals.rowcount, "projects": projects.rowcount, "snapshots": snapshots.rowcount, "recommendations": recommendations.rowcount}, policy_version=policy_version)
    return {"source": source.rowcount, "source_items": items.rowcount, "evidence": evidence.rowcount, "retrievals": retrievals.rowcount, "projects": projects.rowcount, "snapshots": snapshots.rowcount, "recommendations": recommendations.rowcount}


def origin_report(database_url: str, *, include_non_live: bool = False, limit: int = 100) -> dict[str, Any]:
    if not 1 <= limit <= 500:
        raise GovernanceError("limit must be between 1 and 500")
    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT table_name,data_origin,count(*) FROM (
                 SELECT 'sources' table_name,data_origin FROM sources
                 UNION ALL SELECT 'source_items',data_origin FROM source_items
                 UNION ALL SELECT 'evidence_versions',data_origin FROM evidence_versions
                 UNION ALL SELECT 'retrievals',data_origin FROM retrievals
                 UNION ALL SELECT 'collection_runs',data_origin FROM collection_runs
                 UNION ALL SELECT 'daily_riff_runs',data_origin FROM daily_riff_runs
                 UNION ALL SELECT 'github_project_inventory',data_origin FROM github_project_inventory
                 UNION ALL SELECT 'github_project_snapshots',data_origin FROM github_project_snapshots
                 UNION ALL SELECT 'project_recommendations',data_origin FROM project_recommendations
               ) grouped
               WHERE (%s OR data_origin NOT IN ('FIXTURE','TEST','QUARANTINED'))
               GROUP BY table_name,data_origin ORDER BY table_name,data_origin LIMIT %s""",
            (include_non_live, limit),
        ).fetchall()
    return {"include_non_live": include_non_live, "rows": [{"table": _text(row[0]), "data_origin": _text(row[1]), "count": int(row[2])} for row in rows]}


def cleanup_preview(database_url: str, *, origin: str, owner: str, policy_version: str = "governance-v1", limit: int = 500) -> dict[str, Any]:
    if origin not in {"FIXTURE", "TEST"} or not owner.strip():
        raise GovernanceError("cleanup requires FIXTURE or TEST origin and an owner")
    if not 1 <= limit <= 500:
        raise GovernanceError("limit must be between 1 and 500")
    with connection(database_url) as conn:
        rows = conn.execute("SELECT project_id,display_name FROM github_project_inventory WHERE data_origin=%s AND origin_owner=%s ORDER BY project_id LIMIT %s", (origin, owner, limit)).fetchall()
        projects = [{"project_id": _text(row[0]), "display_name": _text(row[1])} for row in rows]
        project_ids = [item["project_id"] for item in projects]
        recommendation_count = int(conn.execute("SELECT count(*) FROM project_recommendations WHERE project_id = ANY(%s) AND data_origin=%s AND origin_owner=%s", (project_ids or ["__none__"], origin, owner)).fetchone()[0])
        snapshot_count = int(conn.execute("SELECT count(*) FROM github_project_snapshots WHERE project_id = ANY(%s) AND data_origin=%s AND origin_owner=%s", (project_ids or ["__none__"], origin, owner)).fetchone()[0])
        exploration_count = int(conn.execute("SELECT count(*) FROM explorations WHERE target_project_id = ANY(%s)", (project_ids or ["__none__"],)).fetchone()[0])
    plan = {"projects": projects, "project_count": len(projects), "recommendation_count": recommendation_count, "snapshot_count": snapshot_count, "exploration_dependency_count": exploration_count, "safe": exploration_count == 0}
    selector = {"origin": origin, "owner": owner}
    with connection(database_url) as conn:
        audit_id = _audit(conn, "PREVIEW", "PLANNED", selector, plan, policy_version=policy_version)
    return {"audit_id": audit_id, "selector": selector, "plan": plan, "input_fingerprint": _fingerprint({"selector": selector, "plan": plan})}


def cleanup_apply(database_url: str, *, origin: str, owner: str, confirmation: str, policy_version: str = "governance-v1") -> dict[str, Any]:
    if confirmation != "CLEANUP":
        raise GovernanceError("cleanup requires confirmation CLEANUP")
    preview = cleanup_preview(database_url, origin=origin, owner=owner, policy_version=policy_version)
    plan = preview["plan"]
    if not plan["safe"]:
        raise GovernanceError("cleanup would orphan an exploration dependency")
    ids = [item["project_id"] for item in plan["projects"]]
    with connection(database_url) as conn:
        if ids:
            conn.execute("DELETE FROM project_recommendations WHERE project_id = ANY(%s) AND data_origin=%s AND origin_owner=%s", (ids, origin, owner))
            conn.execute("DELETE FROM github_project_snapshots WHERE project_id = ANY(%s) AND data_origin=%s AND origin_owner=%s", (ids, origin, owner))
            conn.execute("DELETE FROM github_project_inventory WHERE project_id = ANY(%s) AND data_origin=%s AND origin_owner=%s", (ids, origin, owner))
        audit_id = _audit(conn, "CLEANUP", "APPLIED", {"origin": origin, "owner": owner}, plan, policy_version=policy_version)
    return {"audit_id": audit_id, "deleted": {"projects": len(ids), "snapshots": plan["snapshot_count"], "recommendations": plan["recommendation_count"]}, "input_fingerprint": preview["input_fingerprint"]}


def quarantine(database_url: str, *, table_name: str, row_key: str, raw_payload: Mapping[str, Any], reason_code: str, provenance: Mapping[str, Any] | None = None, policy_version: str = "governance-v1") -> dict[str, Any]:
    if not table_name.strip() or not row_key.strip() or not reason_code.strip():
        raise GovernanceError("table_name, row_key, and reason_code are required")
    quarantine_id = str(uuid.uuid4())
    with connection(database_url) as conn:
        conn.execute("INSERT INTO data_quarantine_records (quarantine_id,table_name,row_key,raw_payload,reason_code,provenance,policy_version) VALUES (%s,%s,%s,%s,%s,%s,%s)", (quarantine_id, table_name, row_key, Jsonb(dict(raw_payload)), reason_code, Jsonb(dict(provenance or {})), policy_version))
        _audit(conn, "QUARANTINE", "APPLIED", {"table_name": table_name, "row_key": row_key}, {"quarantine_id": quarantine_id, "reason_code": reason_code}, policy_version=policy_version)
    return {"quarantine_id": quarantine_id, "table_name": table_name, "row_key": row_key, "reason_code": reason_code, "data_origin": "QUARANTINED"}


def retention_preview(database_url: str, *, older_than_days: int, policy_version: str = "retention-v1") -> dict[str, Any]:
    if older_than_days < 1:
        raise GovernanceError("older_than_days must be positive")
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    with connection(database_url) as conn:
        rows = conn.execute("SELECT run_id,status,started_at,data_origin,origin_owner FROM collection_runs WHERE started_at < %s AND data_origin IN ('FIXTURE','TEST','QUARANTINED') ORDER BY started_at LIMIT 500", (cutoff,)).fetchall()
    plan = {"cutoff": cutoff.isoformat(), "collection_runs": [{"run_id": _text(row[0]), "status": _text(row[1]), "started_at": row[2].isoformat(), "data_origin": _text(row[3]), "origin_owner": _text(row[4]) or None} for row in rows], "action": "ARCHIVE_NON_LIVE_RUNS"}
    with connection(database_url) as conn:
        audit_id = _audit(conn, "RETENTION", "PLANNED", {"older_than_days": older_than_days}, plan, policy_version=policy_version)
    return {"audit_id": audit_id, "plan": plan, "input_fingerprint": _fingerprint(plan), "applied": False}


def retention_apply(database_url: str, *, older_than_days: int, confirmation: str, policy_version: str = "retention-v1") -> dict[str, Any]:
    if confirmation != "RETENTION":
        raise GovernanceError("retention requires confirmation RETENTION")
    preview = retention_preview(database_url, older_than_days=older_than_days, policy_version=policy_version)
    # Collection history is immutable in v0.1; applying retention records an
    # explicit archival decision without deleting evidence or operational rows.
    plan = dict(preview["plan"])
    plan["archived_run_ids"] = [item["run_id"] for item in plan["collection_runs"]]
    with connection(database_url) as conn:
        audit_id = _audit(conn, "RETENTION", "APPLIED", {"older_than_days": older_than_days}, plan, policy_version=policy_version)
    return {"audit_id": audit_id, "archived_count": len(plan["archived_run_ids"]), "input_fingerprint": preview["input_fingerprint"]}


def approve_live_source(
    database_url: str,
    *,
    source_id: str,
    owner: str,
    policy_version: str = "g48-origin-v1",
) -> dict[str, Any]:
    """Explicitly approve one configured source as eligible for live signals."""

    if not source_id.strip() or not owner.strip():
        raise GovernanceError("source_id and owner are required")
    from .evidence import is_fixture_source, is_test_source

    with connection(database_url) as conn:
        row = conn.execute(
            """SELECT s.source_id, s.name, s.canonical_root, s.enabled,
                      COALESCE(s.data_origin, 'UNCLASSIFIED'), c.enabled
               FROM sources s LEFT JOIN ingestion_source_configs c
                 ON c.source_id = s.source_id
               WHERE s.source_id = %s""",
            (source_id,),
        ).fetchone()
        if row is None:
            raise GovernanceError(f"unknown source_id: {source_id}")
        sid, name, root, source_enabled, current_origin, config_enabled = row
        if is_fixture_source(_text(sid), _text(name), _text(root)):
            raise GovernanceError("fixture-like sources cannot be approved as LIVE")
        if not source_enabled or config_enabled is not True:
            raise GovernanceError("source and ingestion configuration must both be enabled")
        if not _text(root):
            raise GovernanceError("source canonical_root is required before live approval")
        result = conn.execute(
            """UPDATE sources
               SET data_origin='LIVE', origin_owner=%s, origin_policy_version=%s
               WHERE source_id=%s""",
            (owner.strip(), policy_version, source_id),
        )
        plan = {
            "source_id": source_id,
            "previous_origin": _text(current_origin),
            "approved": result.rowcount == 1,
            "owner": owner.strip(),
        }
        audit_id = _audit(
            conn, "BACKFILL", "APPLIED",
            {"source_id": source_id, "action": "APPROVE_LIVE_SOURCE"},
            plan, policy_version=policy_version,
        )
    return {"audit_id": audit_id, **plan, "data_origin": "LIVE"}


def origin_audit(database_url: str, *, limit: int = 100) -> dict[str, Any]:
    """Return bounded provenance anomalies without mutating persisted data."""

    if not 1 <= limit <= 500:
        raise GovernanceError("limit must be between 1 and 500")
    from .evidence import is_fixture_source, is_test_source

    with connection(database_url) as conn:
        origins = conn.execute(
            """SELECT table_name, COALESCE(data_origin, 'UNCLASSIFIED'), count(*)
               FROM (
                 SELECT 'sources' table_name, data_origin FROM sources
                 UNION ALL SELECT 'source_items', data_origin FROM source_items
                 UNION ALL SELECT 'evidence_versions', data_origin FROM evidence_versions
                 UNION ALL SELECT 'retrievals', data_origin FROM retrievals
               ) grouped
               GROUP BY table_name, data_origin ORDER BY table_name, data_origin"""
        ).fetchall()
        live_mismatch = conn.execute(
            """SELECT e.evidence_id, si.source_id, s.name,
                      COALESCE(e.data_origin,'UNCLASSIFIED'),
                      COALESCE(s.data_origin,'UNCLASSIFIED'),
                      COALESCE(si.data_origin,'UNCLASSIFIED'),
                      s.enabled, s.origin_owner
               FROM evidence_versions e
               JOIN source_items si ON si.source_item_id=e.source_item_id
               JOIN sources s ON s.source_id=si.source_id
               WHERE COALESCE(e.data_origin,'UNCLASSIFIED')='LIVE'
                 AND (COALESCE(s.data_origin,'UNCLASSIFIED') <> 'LIVE'
                      OR COALESCE(si.data_origin,'UNCLASSIFIED') <> 'LIVE'
                      OR NOT s.enabled)
               ORDER BY e.retrieved_at, e.evidence_id LIMIT %s""",
            (limit,),
        ).fetchall()
        unclassified_runs = conn.execute(
            """SELECT run_id, source_ids, COALESCE(data_origin,'UNCLASSIFIED'), origin_reason
               FROM collection_runs
               WHERE COALESCE(data_origin,'UNCLASSIFIED')='UNCLASSIFIED'
               ORDER BY started_at DESC, run_id LIMIT %s""",
            (limit,),
        ).fetchall()
        fixture_live = conn.execute(
            """SELECT source_id, name, COALESCE(data_origin,'UNCLASSIFIED')
               FROM sources
               WHERE COALESCE(data_origin,'UNCLASSIFIED')='LIVE'
               ORDER BY source_id LIMIT %s""",
            (limit,),
        ).fetchall()
        unreviewed = conn.execute(
            """SELECT s.source_id, s.name, COALESCE(s.data_origin,'UNCLASSIFIED'),
                      s.enabled, c.enabled
               FROM sources s LEFT JOIN ingestion_source_configs c
                 ON c.source_id=s.source_id
               WHERE COALESCE(s.data_origin,'UNCLASSIFIED') <> 'LIVE'
               ORDER BY s.name LIMIT %s""",
            (limit,),
        ).fetchall()
    fixture_marked_live = [
        {"source_id": _text(row[0]), "name": _text(row[1]), "data_origin": _text(row[2])}
        for row in fixture_live
        if is_fixture_source(_text(row[0]), _text(row[1]))
    ]
    return {
        "rows_by_origin": [
            {"table": _text(row[0]), "data_origin": _text(row[1]), "count": int(row[2])}
            for row in origins
        ],
        "anomalies": {
            "live_evidence_without_trusted_source": [
                {
                    "evidence_id": _text(row[0]), "source_id": _text(row[1]),
                    "source_name": _text(row[2]), "evidence_origin": _text(row[3]),
                    "source_origin": _text(row[4]),
                    "source_item_origin": _text(row[5]),
                    "source_enabled": bool(row[6]),
                    "owner": _text(row[7]) or None,
                    "reason_code": (
                        "DISABLED_SOURCE" if not row[6]
                        else "SOURCE_NOT_APPROVED" if _text(row[4]) != "LIVE"
                        else "SOURCE_ITEM_ORIGIN_MISMATCH" if _text(row[5]) != "LIVE"
                        else "EVIDENCE_ORIGIN_MISMATCH"
                    ),
                }
                for row in live_mismatch
            ],
            "unclassified_collection_runs": [
                {
                    "run_id": _text(row[0]),
                    "source_ids": [_text(value) for value in (_json(row[1], []) or [])],
                    "data_origin": _text(row[2]),
                    "reason_code": _text(row[3]) or "RUN_ORIGIN_UNRESOLVED",
                }
                for row in unclassified_runs
            ],
            "fixture_marked_live_sources": fixture_marked_live,
            "unreviewed_sources": [
                {
                    "source_id": _text(row[0]), "name": _text(row[1]),
                    "data_origin": _text(row[2]), "source_enabled": bool(row[3]),
                    "config_enabled": row[4] is True,
                }
                for row in unreviewed
            ],
        },
    }


def live_source_health_report(database_url: str, *, limit: int = 100) -> dict[str, Any]:
    'Describe whether each configured source can contribute trusted live data.'

    if not 1 <= limit <= 500:
        raise GovernanceError('limit must be between 1 and 500')
    from .evidence import is_fixture_source

    with connection(database_url) as conn:
        rows = conn.execute(
            '''SELECT s.source_id, s.source_type, s.name, s.canonical_root,
                      s.enabled, COALESCE(s.data_origin,'UNCLASSIFIED'),
                      s.origin_owner, c.enabled, c.endpoint,
                      c.config_version, c.cursor_kind,
                      latest.run_id, latest.status, latest.policy_version,
                      latest.started_at, latest.finished_at, latest.origin_reason,
                      count(DISTINCT CASE WHEN COALESCE(e.data_origin,'UNCLASSIFIED')='LIVE'
                                           AND COALESCE(si.data_origin,'UNCLASSIFIED')='LIVE'
                                           AND COALESCE(s.data_origin,'UNCLASSIFIED')='LIVE'
                                           AND s.enabled
                                      THEN e.evidence_id END),
                      count(DISTINCT e.evidence_id)
               FROM sources s
               LEFT JOIN ingestion_source_configs c ON c.source_id=s.source_id
               LEFT JOIN source_items si ON si.source_id=s.source_id
               LEFT JOIN evidence_versions e ON e.source_item_id=si.source_item_id
               LEFT JOIN LATERAL (
                   SELECT cr.run_id, cr.status, cr.policy_version, cr.started_at,
                          cr.finished_at, cr.origin_reason
                   FROM collection_runs cr
                   WHERE EXISTS (
                       SELECT 1
                       FROM jsonb_array_elements_text(cr.source_ids) AS source_ref(source_id)
                       WHERE source_ref.source_id = s.source_id
                   )
                   ORDER BY cr.started_at DESC, cr.run_id DESC
                   LIMIT 1
               ) latest ON TRUE
               GROUP BY s.source_id, s.source_type, s.name, s.canonical_root,
                        s.enabled, s.data_origin, s.origin_owner, c.enabled,
                        c.endpoint, c.config_version, c.cursor_kind,
                        latest.run_id, latest.status, latest.policy_version,
                        latest.started_at, latest.finished_at, latest.origin_reason
               ORDER BY s.name LIMIT %s''',
            (limit,),
        ).fetchall()
    sources = []
    for row in rows:
        (sid, stype, name, root, enabled, origin, owner, config_enabled, endpoint,
         config_version, cursor_kind, latest_run_id, latest_status,
         latest_policy_version, latest_started_at, latest_finished_at,
         latest_origin_reason, trusted_count, evidence_count) = row
        fixture = is_fixture_source(_text(sid), _text(name), _text(root))
        if fixture or _text(origin) in {'FIXTURE', 'TEST', 'QUARANTINED'}:
            state = 'FIXTURE_ONLY'
        elif not enabled or config_enabled is not True:
            state = 'DISABLED'
        elif _text(origin) != 'LIVE':
            state = 'REVIEW_REQUIRED'
        elif not endpoint:
            state = 'UNCONFIGURED'
        elif latest_status == 'FAILED':
            state = 'FAILED'
        elif latest_status == 'PARTIAL':
            state = 'PARTIAL'
        elif latest_status == 'RUNNING':
            state = 'RUNNING'
        elif latest_status is None:
            state = 'NEVER_COLLECTED'
        elif int(trusted_count) == 0:
            state = 'EMPTY'
        else:
            state = 'USABLE'
        sources.append({
            'source_id': _text(sid), 'source_type': _text(stype), 'name': _text(name),
            'canonical_root': _text(root) or None,
            'owner': _text(owner) or None,
            'data_origin': _text(origin), 'enabled': bool(enabled),
            'config_enabled': config_enabled is True, 'state': state,
            'fetch_policy': {
                'endpoint': _text(endpoint) or None,
                'config_version': int(config_version) if config_version is not None else None,
                'cursor_kind': _text(cursor_kind) or None,
            },
            'latest_health': {
                'run_id': _text(latest_run_id) or None,
                'status': _text(latest_status) or None,
                'policy_version': _text(latest_policy_version) or None,
                'started_at': latest_started_at,
                'finished_at': latest_finished_at,
                'origin_reason': _text(latest_origin_reason) or None,
            } if latest_run_id else None,
            'trusted_live_evidence_count': int(trusted_count),
            'evidence_count': int(evidence_count),
        })
    return {
        'source_count': len(sources),
        'state_counts': {
            state: sum(1 for item in sources if item['state'] == state)
            for state in sorted({item['state'] for item in sources})
        },
        'sources': sources,
    }


def repair_origins(
    database_url: str,
    *,
    limit: int = 5000,
    policy_version: str = "g48-origin-v1",
) -> dict[str, Any]:
    """Repair provenance metadata and quarantine unsafe LIVE evidence.

    No evidence is deleted. Explicit fixture and generated-test identities are
    classified and disabled, unsafe legacy LIVE rows are quarantined, and
    unresolved collection runs receive a reason rather than being silently
    promoted.
    """

    if not 1 <= limit <= 5000:
        raise GovernanceError("limit must be between 1 and 5000")
    from .evidence import is_fixture_source, is_test_source

    with connection(database_url) as conn:
        source_rows = conn.execute(
            """SELECT source_id, name, canonical_root, COALESCE(data_origin,'UNCLASSIFIED')
               FROM sources ORDER BY source_id"""
        ).fetchall()
        fixture_sources = [
            _text(row[0]) for row in source_rows
            if is_fixture_source(_text(row[0]), _text(row[1]), _text(row[2]))
        ]
        test_sources = [
            _text(row[0]) for row in source_rows
            if _text(row[0]) not in fixture_sources
            and is_test_source(_text(row[0]), _text(row[1]), _text(row[2]))
        ]
        fixture_source_count = fixture_item_count = fixture_evidence_count = fixture_retrieval_count = 0
        if fixture_sources:
            fixture_source_count = conn.execute(
                """UPDATE sources SET data_origin='FIXTURE', origin_owner='origin-repair',
                       origin_policy_version=%s
                   WHERE source_id=ANY(%s) AND COALESCE(data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, fixture_sources),
            ).rowcount
            fixture_item_count = conn.execute(
                """UPDATE source_items SET data_origin='FIXTURE', origin_owner='origin-repair',
                       origin_policy_version=%s
                   WHERE source_id=ANY(%s) AND COALESCE(data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, fixture_sources),
            ).rowcount
            fixture_evidence_count = conn.execute(
                """UPDATE evidence_versions e SET data_origin='FIXTURE',
                       origin_owner='origin-repair', origin_policy_version=%s
                   FROM source_items si
                   WHERE si.source_item_id=e.source_item_id AND si.source_id=ANY(%s)
                     AND COALESCE(e.data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, fixture_sources),
            ).rowcount
            fixture_retrieval_count = conn.execute(
                """UPDATE retrievals r SET data_origin='FIXTURE',
                       origin_owner='origin-repair', origin_policy_version=%s
                   FROM evidence_versions e JOIN source_items si ON si.source_item_id=e.source_item_id
                   WHERE e.evidence_id=r.evidence_id AND si.source_id=ANY(%s)
                     AND COALESCE(r.data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, fixture_sources),
            ).rowcount

        test_source_count = test_item_count = test_evidence_count = test_retrieval_count = 0
        if test_sources:
            test_source_count = conn.execute(
                """UPDATE sources SET data_origin='TEST', origin_owner='test-source-repair',
                       enabled=FALSE, origin_policy_version=%s
                   WHERE source_id=ANY(%s) AND COALESCE(data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, test_sources),
            ).rowcount
            conn.execute("UPDATE ingestion_source_configs SET enabled=FALSE WHERE source_id=ANY(%s)", (test_sources,))
            test_item_count = conn.execute(
                """UPDATE source_items SET data_origin='TEST', origin_owner='test-source-repair',
                       origin_policy_version=%s
                   WHERE source_id=ANY(%s) AND COALESCE(data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, test_sources),
            ).rowcount
            test_evidence_count = conn.execute(
                """UPDATE evidence_versions e SET data_origin='TEST',
                       origin_owner='test-source-repair', origin_policy_version=%s
                   FROM source_items si
                   WHERE si.source_item_id=e.source_item_id AND si.source_id=ANY(%s)
                     AND COALESCE(e.data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, test_sources),
            ).rowcount
            test_retrieval_count = conn.execute(
                """UPDATE retrievals r SET data_origin='TEST',
                       origin_owner='test-source-repair', origin_policy_version=%s
                   FROM evidence_versions e JOIN source_items si ON si.source_item_id=e.source_item_id
                   WHERE e.evidence_id=r.evidence_id AND si.source_id=ANY(%s)
                     AND COALESCE(r.data_origin,'UNCLASSIFIED')<>'FIXTURE'""",
                (policy_version, test_sources),
            ).rowcount

        rows = conn.execute(
            """SELECT e.evidence_id, si.source_id, s.name, e.data_origin,
                      e.origin_owner, e.origin_run_id, e.origin_policy_version
               FROM evidence_versions e
               JOIN source_items si ON si.source_item_id=e.source_item_id
               JOIN sources s ON s.source_id=si.source_id
               WHERE COALESCE(e.data_origin,'UNCLASSIFIED')='LIVE'
                 AND COALESCE(s.data_origin,'UNCLASSIFIED') NOT IN ('LIVE','FIXTURE','TEST')
               ORDER BY e.retrieved_at, e.evidence_id LIMIT %s""",
            (limit,),
        ).fetchall()
        quarantined = 0
        for evidence_id, source_id, name, old_origin, old_owner, run_id, old_policy in rows:
            payload = {
                "evidence_id": _text(evidence_id), "source_id": _text(source_id),
                "source_name": _text(name), "previous_data_origin": _text(old_origin),
                "previous_origin_owner": _text(old_owner),
            }
            conn.execute(
                """INSERT INTO data_quarantine_records
                   (quarantine_id, table_name, row_key, raw_payload, reason_code,
                    provenance, policy_version)
                   VALUES (%s,'evidence_versions',%s,%s,'LIVE_SOURCE_NOT_APPROVED',%s,%s)""",
                (str(uuid.uuid4()), _text(evidence_id), Jsonb(payload),
                 Jsonb({"source_id": _text(source_id), "origin_run_id": _text(run_id),
                        "origin_policy_version": _text(old_policy)}), policy_version),
            )
            conn.execute(
                """UPDATE evidence_versions SET data_origin='QUARANTINED',
                       origin_owner='origin-repair', origin_policy_version=%s
                   WHERE evidence_id=%s""",
                (policy_version, evidence_id),
            )
            conn.execute(
                """UPDATE retrievals SET data_origin='QUARANTINED',
                       origin_owner='origin-repair', origin_policy_version=%s
                   WHERE evidence_id=%s AND COALESCE(data_origin,'UNCLASSIFIED')='LIVE'""",
                (policy_version, evidence_id),
            )
            quarantined += 1

        repaired_runs = 0
        unresolved_runs = 0
        run_rows = conn.execute(
            """SELECT run_id, source_ids FROM collection_runs
               WHERE COALESCE(data_origin,'UNCLASSIFIED')='UNCLASSIFIED'
               ORDER BY started_at LIMIT %s""",
            (limit,),
        ).fetchall()
        for run_id, raw_source_ids in run_rows:
            source_ids = [_text(value) for value in (_json(raw_source_ids, []) or [])]
            origin, owner, reason = resolve_collection_origin(conn, source_ids)
            if origin != "UNCLASSIFIED":
                conn.execute(
                    """UPDATE collection_runs SET data_origin=%s, origin_owner=%s,
                           origin_run_id=%s, origin_policy_version=%s,
                           origin_reason='REPAIRED_FROM_SOURCE_REGISTRY'
                       WHERE run_id=%s""",
                    (origin, owner, _text(run_id), policy_version, run_id),
                )
                repaired_runs += 1
            else:
                conn.execute(
                    "UPDATE collection_runs SET origin_reason=%s WHERE run_id=%s AND origin_reason IS NULL",
                    (reason or "RUN_ORIGIN_UNRESOLVED", run_id),
                )
                unresolved_runs += 1

        plan = {
            "fixture_source_ids": fixture_sources,
            "fixture_source_count": fixture_source_count,
            "fixture_source_item_count": fixture_item_count,
            "fixture_evidence_count": fixture_evidence_count,
            "fixture_retrieval_count": fixture_retrieval_count,
            "test_source_ids": test_sources,
            "test_source_count": test_source_count,
            "test_source_item_count": test_item_count,
            "test_evidence_count": test_evidence_count,
            "test_retrieval_count": test_retrieval_count,
            "quarantined_live_evidence_count": quarantined,
            "repaired_collection_run_count": repaired_runs,
            "unresolved_collection_run_count": unresolved_runs,
            "quarantine_limit": limit,
        }
        audit_id = _audit(
            conn, "BACKFILL", "APPLIED",
            {"action": "REPAIR_ORIGINS", "limit": limit},
            plan, policy_version=policy_version,
        )
    return {"audit_id": audit_id, **plan, "non_destructive": True}
