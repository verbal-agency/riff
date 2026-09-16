"""Origin-aware cleanup, quarantine, and retention controls (G35)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection

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
