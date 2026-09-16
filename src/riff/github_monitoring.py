"""Explicit GitHub watches and bounded quantitative discovery (G34).

This module deliberately keeps monitoring separate from the reviewed source
registry. A watch may collect only an already configured G03 source; discovery
can queue candidates, but never enables collection implicitly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from .db import connection
from .evidence_repository import EvidenceRepository
from .github_ingestion import GitHubIngestionRunner, GitHubFetcher
from .ingestion_repository import IngestionRepository
from .project_map import ProjectMapRepository


class GitHubMonitoringError(ValueError):
    """A watch, run, or quantitative rule is invalid."""


class WatchStatus:
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REVOKED = "REVOKED"


class CandidateDisposition:
    AUTO_QUEUED = "AUTO_QUEUED"
    DISABLED_SCOPE_PROPOSED = "DISABLED_SCOPE_PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"


@dataclass(frozen=True, slots=True)
class QuantitativeRule:
    rule_id: str
    policy_version: str
    min_independent_roots: int = 2
    min_relevant_sources: int = 1
    max_candidates: int = 20
    max_requests: int = 10
    popularity_only_stars: int = 50_000
    action: str = "QUEUE"

    def validate(self) -> "QuantitativeRule":
        if not self.rule_id.strip() or not self.policy_version.strip():
            raise GitHubMonitoringError("rule_id and policy_version are required")
        if self.min_independent_roots < 1 or self.min_relevant_sources < 1:
            raise GitHubMonitoringError("independence bounds must be positive")
        if not 1 <= self.max_candidates <= 100 or not 1 <= self.max_requests <= 50:
            raise GitHubMonitoringError("search bounds exceed the safe limit")
        if self.popularity_only_stars < 1:
            raise GitHubMonitoringError("popularity_only_stars must be positive")
        if self.action not in {"QUEUE", "PROPOSE_DISABLED_SCOPE"}:
            raise GitHubMonitoringError("action must be QUEUE or PROPOSE_DISABLED_SCOPE")
        return self


@dataclass(frozen=True, slots=True)
class RepositoryWatch:
    watch_id: str
    provider_repository_id: str
    source_id: str
    project_id: str | None
    status: str
    scope: dict[str, Any]
    cadence_seconds: int
    policy_version: str
    last_run_id: str | None
    last_success_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode()
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value.decode() if isinstance(value, bytes) else value)
        except (ValueError, TypeError):
            return default
    return value if value is not None else default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _independence(candidate: Mapping[str, Any]) -> tuple[int, int]:
    roots = candidate.get("independent_roots", candidate.get("roots", []))
    if isinstance(roots, str):
        roots = [roots]
    root_count = len({str(value).strip() for value in roots if str(value).strip()})
    if not root_count and candidate.get("root_id"):
        root_count = 1
    sources = candidate.get("source_count", candidate.get("independent_sources", []))
    source_count = len(sources) if isinstance(sources, list) else int(sources or 0)
    if not source_count:
        source_count = int(candidate.get("evidence_count", 0) or 0)
    return root_count, source_count


def evaluate_quantitative_search(
    candidates: list[Mapping[str, Any]],
    *,
    query: str,
    rule: QuantitativeRule,
    request_count: int = 1,
    page_count: int = 1,
) -> dict[str, Any]:
    """Filter and rank recorded/live search rows deterministically."""

    rule.validate()
    if not query.strip() or request_count < 1 or page_count < 1:
        raise GitHubMonitoringError("query and request/page counts are required")
    if request_count > rule.max_requests:
        raise GitHubMonitoringError("search request bound exceeded")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for raw in candidates:
        item = dict(raw)
        provider_id = _text(item.get("provider_repository_id") or item.get("id"))
        full_name = _text(item.get("full_name") or item.get("name"))
        storage_provider_id = provider_id or "omitted:" + hashlib.sha256(full_name.encode()).hexdigest()[:24]
        reasons: list[str] = []
        if not provider_id or not full_name:
            reasons.append("MISSING_IDENTITY")
        if provider_id in seen_ids or full_name.lower() in seen_names:
            reasons.append("DUPLICATE_OR_ALIAS")
        if item.get("duplicate_of") or item.get("is_fork") or item.get("fork"):
            reasons.append("FORK_OR_DUPLICATE")
        if item.get("is_mirror") or item.get("mirror"):
            reasons.append("MIRROR")
        if item.get("bot_only"):
            reasons.append("BOT_ONLY")
        if item.get("archived"):
            reasons.append("ARCHIVED")
        stars = item.get("stars", item.get("stargazers_count"))
        if stars is not None and int(stars) >= rule.popularity_only_stars and not item.get("relevant", False):
            reasons.append("POPULARITY_ONLY")
        roots, source_count = _independence(item)
        if roots < rule.min_independent_roots:
            reasons.append("INSUFFICIENT_INDEPENDENCE")
        if source_count < rule.min_relevant_sources:
            reasons.append("INSUFFICIENT_EVIDENCE")
        evaluation = {
            "query": query,
            "rule_id": rule.rule_id,
            "policy_version": rule.policy_version,
            "independent_root_count": roots,
            "relevant_source_count": source_count,
            "request_count": request_count,
            "page_count": page_count,
            "thresholds": {
                "min_independent_roots": rule.min_independent_roots,
                "min_relevant_sources": rule.min_relevant_sources,
                "popularity_only_stars": rule.popularity_only_stars,
            },
            "reasons": reasons,
        }
        item["threshold_evaluation"] = evaluation
        item["uncertainty"] = list(dict.fromkeys([*(item.get("uncertainty") or []), *reasons]))
        item["candidate_id"] = _text(item.get("candidate_id")) or "candidate-" + hashlib.sha256(storage_provider_id.encode()).hexdigest()[:16]
        item["provider_repository_id"] = storage_provider_id
        item["disposition"] = rule.action == "PROPOSE_DISABLED_SCOPE" and CandidateDisposition.DISABLED_SCOPE_PROPOSED or CandidateDisposition.AUTO_QUEUED
        if reasons:
            item["disposition"] = "REJECTED"
            rejected.append(item)
        elif len(accepted) < rule.max_candidates:
            accepted.append(item)
            seen_ids.add(provider_id)
            seen_names.add(full_name.lower())
        else:
            item["disposition"] = "REJECTED"
            item["uncertainty"] = [*item["uncertainty"], "MAX_CANDIDATES"]
            rejected.append(item)
    return {
        "schema_version": 1,
        "query": query.strip(),
        "rule": asdict(rule),
        "request_count": request_count,
        "page_count": page_count,
        "input_fingerprint": _fingerprint({"query": query, "rule": asdict(rule), "candidates": candidates}),
        "accepted": accepted,
        "rejected": rejected,
    }


class GitHubMonitoringRepository:
    """Persistence boundary for explicit watches and discovery candidates."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def resolve_repository(self, reference: str) -> tuple[str, str, str, str | None]:
        value = _text(reference)
        if not value:
            raise GitHubMonitoringError("repository reference is required")
        with connection(self.database_url) as conn:
            rows = conn.execute(
                "SELECT provider_repository_id, source_id, canonical_url, project_id FROM github_repositories "
                "LEFT JOIN github_project_inventory USING (provider_repository_id) "
                "WHERE provider_repository_id = %s OR lower(owner_login || '/' || name) = lower(%s) "
                "OR lower(canonical_url) = lower(%s)", (value, value, value)
            ).fetchall()
        if not rows:
            raise GitHubMonitoringError("repository is not ingested; observe/select it through G03/G33 first")
        if len(rows) > 1:
            raise GitHubMonitoringError("repository reference is ambiguous")
        return tuple(_text(value) if value is not None else None for value in rows[0])  # type: ignore[return-value]

    def create_watch(
        self,
        repository: str,
        *,
        cadence_seconds: int = 86_400,
        policy_version: str = "github-monitor-v1",
        scope: Mapping[str, Any] | None = None,
    ) -> RepositoryWatch:
        if cadence_seconds < 60 or not _text(policy_version):
            raise GitHubMonitoringError("cadence must be at least one minute and policy_version is required")
        provider_id, source_id, _url, project_id = self.resolve_repository(repository)
        watch_id = "github-watch-" + hashlib.sha256(provider_id.encode()).hexdigest()[:24]
        with connection(self.database_url) as conn:
            configured = conn.execute("SELECT 1 FROM ingestion_source_configs WHERE source_id = %s", (source_id,)).fetchone()
            if configured is None:
                raise GitHubMonitoringError("repository source has no G03 ingestion configuration")
            conn.execute(
                """INSERT INTO github_repository_watches
                (watch_id, provider_repository_id, project_id, source_id, status, scope, cadence_seconds, policy_version)
                VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s,%s)
                ON CONFLICT (provider_repository_id) DO UPDATE SET status='ACTIVE', scope=EXCLUDED.scope,
                cadence_seconds=EXCLUDED.cadence_seconds, policy_version=EXCLUDED.policy_version, updated_at=now()""",
                (watch_id, provider_id, project_id, source_id, Jsonb(dict(scope or {"artifacts": ["repository", "releases", "issues", "readme"]})), cadence_seconds, policy_version),
            )
            conn.execute("INSERT INTO github_watch_events (event_id,watch_id,event_type,reason,policy_version) VALUES (%s,%s,'CREATED',%s,%s)", (str(uuid.uuid4()), watch_id, "explicit user-approved watch", policy_version))
        return self.get_watch(watch_id)

    def get_watch(self, watch_id: str) -> RepositoryWatch:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT watch_id,provider_repository_id,source_id,project_id,status,scope,cadence_seconds,policy_version,last_run_id,last_success_at FROM github_repository_watches WHERE watch_id=%s", (_text(watch_id),)).fetchone()
        if row is None:
            raise GitHubMonitoringError("watch not found")
        return RepositoryWatch(_text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]) or None, _text(row[4]), _json(row[5], {}), int(row[6]), _text(row[7]), _text(row[8]) or None, row[9])

    def list_watches(self) -> list[dict[str, Any]]:
        with connection(self.database_url) as conn:
            ids = [row[0] for row in conn.execute("SELECT watch_id FROM github_repository_watches ORDER BY created_at").fetchall()]
        return [self.get_watch(_text(item)).to_dict() for item in ids]

    def set_status(self, watch_id: str, status: str, *, reason: str) -> RepositoryWatch:
        if status not in {WatchStatus.DISABLED, WatchStatus.REVOKED, WatchStatus.ACTIVE}:
            raise GitHubMonitoringError("invalid watch status")
        watch = self.get_watch(watch_id)
        with connection(self.database_url) as conn:
            conn.execute("UPDATE github_repository_watches SET status=%s,updated_at=now() WHERE watch_id=%s", (status, watch.watch_id))
            event = "DISABLED" if status == WatchStatus.DISABLED else "REVOKED" if status == WatchStatus.REVOKED else "CREATED"
            conn.execute("INSERT INTO github_watch_events (event_id,watch_id,event_type,reason,policy_version) VALUES (%s,%s,%s,%s,%s)", (str(uuid.uuid4()), watch.watch_id, event, _text(reason) or "operator status change", watch.policy_version))
        return self.get_watch(watch.watch_id)

    def run_watch(self, watch_id: str, *, fetcher: GitHubFetcher, max_pages: int = 10) -> dict[str, Any]:
        watch = self.get_watch(watch_id)
        if watch.status != WatchStatus.ACTIVE:
            return {"status": "SKIPPED", "watch": watch.to_dict(), "reason": "watch is disabled or revoked"}
        before = {kind: IngestionRepository(self.database_url).get_cursor(watch.source_id, f"github:{kind}") for kind in ("releases", "issues")}
        monitor_id = str(uuid.uuid4())
        with connection(self.database_url) as conn:
            conn.execute("INSERT INTO github_monitor_runs (monitor_run_id,watch_id,status,policy_version,input_fingerprint,cursor_before) VALUES (%s,%s,'RUNNING',%s,%s,%s)", (monitor_id, watch.watch_id, watch.policy_version, _fingerprint({"watch": watch.to_dict(), "cursor": before}), Jsonb(before)))
        try:
            summary = GitHubIngestionRunner(IngestionRepository(self.database_url), EvidenceRepository(self.database_url), fetcher, max_pages=max_pages).run(source_ids=[watch.source_id], policy_version=watch.policy_version)
        except Exception as exc:
            with connection(self.database_url) as conn:
                conn.execute("UPDATE github_monitor_runs SET status='FAILED',error=%s,finished_at=now() WHERE monitor_run_id=%s", (Jsonb({"type": type(exc).__name__, "message": str(exc)[:500]}), monitor_id))
            raise
        status_value = summary.status.value if hasattr(summary.status, "value") else str(summary.status)
        after = {kind: IngestionRepository(self.database_url).get_cursor(watch.source_id, f"github:{kind}") for kind in ("releases", "issues")}
        snapshot_id = None
        if watch.project_id and summary.stored:
            snapshot_id = ProjectMapRepository(self.database_url).refresh(watch.project_id, policy_version=watch.policy_version).snapshot_id
        failed = summary.failed_transient + summary.failed_permanent
        with connection(self.database_url) as conn:
            conn.execute("UPDATE github_monitor_runs SET status=%s,collection_run_id=%s,project_snapshot_id=%s,stored_count=%s,duplicate_count=%s,failed_count=%s,cursor_after=%s,finished_at=now() WHERE monitor_run_id=%s", (status_value, summary.run_id, snapshot_id, summary.stored, summary.duplicates, failed, Jsonb(after), monitor_id))
            conn.execute("UPDATE github_repository_watches SET last_run_id=%s,last_success_at=CASE WHEN %s IN ('SUCCEEDED','PARTIAL') THEN now() ELSE last_success_at END,updated_at=now() WHERE watch_id=%s", (monitor_id, status_value, watch.watch_id))
        return {"monitor_run_id": monitor_id, "watch": self.get_watch(watch.watch_id).to_dict(), "collection_run_id": summary.run_id, "status": status_value, "stored": summary.stored, "duplicates": summary.duplicates, "failed": failed, "cursor_before": before, "cursor_after": after, "project_snapshot_id": snapshot_id}

    def persist_search(self, result: Mapping[str, Any]) -> dict[str, Any]:
        rule = dict(result["rule"])
        discovery_id = "github-discovery-" + _fingerprint({"query": result["query"], "rule": rule, "input": result["input_fingerprint"]})[:24]
        with connection(self.database_url) as conn:
            conn.execute("INSERT INTO github_discovery_runs (discovery_run_id,query,rule_id,policy_version,input_fingerprint,request_count,page_count,candidate_count,threshold_evaluation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (discovery_run_id) DO NOTHING", (discovery_id, result["query"], rule["rule_id"], rule["policy_version"], result["input_fingerprint"], result["request_count"], result["page_count"], len(result["accepted"]), Jsonb({"accepted": len(result["accepted"]), "rejected": len(result["rejected"])})))
            for item in [*result["accepted"], *result["rejected"]]:
                conn.execute("INSERT INTO github_discovery_candidates (candidate_id,discovery_run_id,provider_repository_id,full_name,canonical_url,disposition,rule_id,policy_version,root_id,correlation_metadata,threshold_evaluation,evidence_ids,uncertainty) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (candidate_id) DO UPDATE SET disposition=EXCLUDED.disposition,updated_at=now()", (item["candidate_id"], discovery_id, _text(item.get("provider_repository_id") or item.get("id")), _text(item.get("full_name") or item.get("name")), _text(item.get("canonical_url") or item.get("html_url")), item["disposition"], rule["rule_id"], rule["policy_version"], item.get("root_id"), Jsonb(item.get("correlation_metadata") or {}), Jsonb(item["threshold_evaluation"]), Jsonb(item.get("artifact_ids") or []), Jsonb(item.get("uncertainty") or [])))
        return {"discovery_run_id": discovery_id, "accepted": len(result["accepted"]), "rejected": len(result["rejected"])}

    def review_candidate(self, candidate_id: str, disposition: str) -> dict[str, Any]:
        if disposition not in {CandidateDisposition.APPROVED, CandidateDisposition.REJECTED}:
            raise GitHubMonitoringError("review disposition must be APPROVED or REJECTED")
        with connection(self.database_url) as conn:
            result = conn.execute("UPDATE github_discovery_candidates SET disposition=%s,updated_at=now() WHERE candidate_id=%s AND disposition IN ('AUTO_QUEUED','DISABLED_SCOPE_PROPOSED')", (disposition, _text(candidate_id)))
            if result.rowcount != 1:
                raise GitHubMonitoringError("candidate not found or is not reviewable")
            row = conn.execute("SELECT candidate_id,full_name,disposition,rule_id,policy_version,threshold_evaluation,uncertainty FROM github_discovery_candidates WHERE candidate_id=%s", (_text(candidate_id),)).fetchone()
        return {"candidate_id": _text(row[0]), "full_name": _text(row[1]), "disposition": _text(row[2]), "rule_id": _text(row[3]), "policy_version": _text(row[4]), "threshold_evaluation": _json(row[5], {}), "uncertainty": _json(row[6], [])}
