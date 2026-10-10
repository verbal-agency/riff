"""Durable, bounded orchestration for the daily Riff funnel (G13)."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .db import connection
from .daily import DailyFixture, load_fixture, seed_fixture
from .riffs import DailyRiffService, DeterministicReasoningProvider, RiffRepository


STAGES = ("COLLECT", "RECEIPT", "CAPABILITY", "PROFILE", "SIGNAL", "RIFF", "PUBLISH")
TERMINAL_STATUSES = {"SUCCEEDED", "EMPTY"}
DEFAULT_LEASE_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class PipelineClaim:
    """A two-value-compatible claim result with operational detail."""

    run_id: str
    claimed: bool
    lease_owner: str | None = None
    reason: str | None = None
    stale_recovered: bool = False

    def __iter__(self):
        yield self.run_id
        yield self.claimed


class PipelineError(ValueError):
    """A bounded pipeline request or persisted run error."""


class PipelineRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def claim(
        self,
        run_date: date,
        policy_version: str,
        *,
        resume: bool = False,
        mode: str = "unknown",
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> PipelineClaim:
        if not 1 <= lease_seconds <= 24 * 60 * 60:
            raise PipelineError("lease_seconds must be between 1 and 86400")
        with connection(self.database_url) as conn:
            run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"riff-pipeline:{run_date.isoformat()}:{policy_version}"))
            lease_owner = str(uuid.uuid4())
            inserted = conn.execute(
                """INSERT INTO pipeline_runs
                   (run_id, run_date, policy_version, status, mode, lease_owner, lease_expires_at, heartbeat_at)
                   VALUES (%s, %s, %s, 'RUNNING', %s, %s, now() + (%s * interval '1 second'), now())
                   ON CONFLICT (run_date, policy_version) DO NOTHING""",
                (run_id, run_date, policy_version, mode, lease_owner, lease_seconds),
            ).rowcount == 1
            row = conn.execute(
                """SELECT run_id, status, lease_owner, lease_expires_at
                   FROM pipeline_runs WHERE run_date = %s AND policy_version = %s FOR UPDATE""",
                (run_date, policy_version),
            ).fetchone()
            if row is None:
                raise PipelineError("pipeline run could not be claimed")
            existing_id, current = str(row[0]), str(row[1])
            prior_owner = str(row[2]) if row[2] else None
            expires_at = row[3]
            if current in TERMINAL_STATUSES:
                self._event(conn, existing_id, "NOOP_TERMINAL_RUN", detail={"reason": "TERMINAL_RUN"})
                return PipelineClaim(existing_id, False, reason="TERMINAL_RUN")
            stale_recovered = False
            if current == "RUNNING" and not inserted:
                if expires_at is not None and expires_at > datetime.now(timezone.utc):
                    self._event(conn, existing_id, "NOOP_ACTIVE_LEASE", prior_owner, detail={"reason": "ACTIVE_LEASE"})
                    return PipelineClaim(existing_id, False, reason="ACTIVE_LEASE")
                if not resume:
                    self._event(conn, existing_id, "NOOP_STALE_REQUIRES_RESUME", prior_owner, detail={"reason": "STALE_RUN_REQUIRES_RESUME"})
                    return PipelineClaim(existing_id, False, reason="STALE_RUN_REQUIRES_RESUME")
                stale_recovered = True
                self._event(conn, existing_id, "STALE_RECLAIMED", prior_owner, lease_owner, {"lease_seconds": lease_seconds})
            elif current == "FAILED" and not resume:
                self._event(conn, existing_id, "NOOP_FAILED_REQUIRES_RESUME", detail={"reason": "FAILED_RUN_REQUIRES_RESUME"})
                return PipelineClaim(existing_id, False, reason="FAILED_RUN_REQUIRES_RESUME")
            elif current == "FAILED":
                self._event(conn, existing_id, "FAILED_RUN_RESUMED", prior_owner, lease_owner, {"lease_seconds": lease_seconds})
            elif inserted:
                self._event(conn, existing_id, "CLAIMED", lease_owner=lease_owner, detail={"lease_seconds": lease_seconds})
            conn.execute(
                """UPDATE pipeline_runs
                   SET status = 'RUNNING', mode = %s, lease_owner = %s,
                       lease_expires_at = now() + (%s * interval '1 second'), heartbeat_at = now(),
                       recovery_count = recovery_count + %s, error = NULL, updated_at = now()
                   WHERE run_id = %s""",
                (mode, lease_owner, lease_seconds, 1 if stale_recovered else 0, existing_id),
            )
            for stage in STAGES:
                conn.execute("INSERT INTO pipeline_stages (stage_id, run_id, stage_name, status, policy_version) VALUES (%s, %s, %s, 'PENDING', %s) ON CONFLICT (run_id, stage_name) DO NOTHING", (str(uuid.uuid5(uuid.NAMESPACE_URL, f"{existing_id}:{stage}")), existing_id, stage, policy_version))
            return PipelineClaim(existing_id, True, lease_owner=lease_owner, reason="STALE_RECLAIMED" if stale_recovered else "CLAIMED", stale_recovered=stale_recovered)

    @staticmethod
    def _event(conn, run_id: str, event_type: str, prior_lease_owner: str | None = None, lease_owner: str | None = None, detail: dict[str, Any] | None = None) -> None:
        conn.execute(
            "INSERT INTO pipeline_run_events (run_id, event_type, prior_lease_owner, lease_owner, detail) VALUES (%s, %s, %s, %s, %s)",
            (run_id, event_type, prior_lease_owner, lease_owner, Jsonb(detail or {})),
        )

    def heartbeat(self, run_id: str, lease_owner: str | None = None, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
        with connection(self.database_url) as conn:
            clauses = ["run_id = %s", "status = 'RUNNING'"]
            params: list[Any] = [lease_seconds, run_id]
            if lease_owner:
                clauses.append("lease_owner = %s")
                params.append(lease_owner)
            result = conn.execute(
                "UPDATE pipeline_runs SET heartbeat_at = now(), lease_expires_at = now() + (%s * interval '1 second'), updated_at = now() WHERE " + " AND ".join(clauses),
                params,
            )
            return result.rowcount == 1

    def begin_stage(self, run_id: str, stage_name: str, *, lease_owner: str | None = None) -> bool:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT status FROM pipeline_stages WHERE run_id = %s AND stage_name = %s FOR UPDATE", (run_id, stage_name)).fetchone()
            if row is None:
                raise PipelineError(f"unknown pipeline stage: {stage_name}")
            if str(row[0]) == "COMPLETE":
                return False
            conn.execute("UPDATE pipeline_stages SET status = 'RUNNING', attempt_count = attempt_count + 1, started_at = now(), error = NULL WHERE run_id = %s AND stage_name = %s", (run_id, stage_name))
            predicate = "run_id = %s" + (" AND lease_owner = %s" if lease_owner else "")
            params: list[Any] = [stage_name, run_id] + ([lease_owner] if lease_owner else [])
            result = conn.execute("UPDATE pipeline_runs SET current_stage = %s, heartbeat_at = now(), lease_expires_at = now() + (%s * interval '1 second'), updated_at = now() WHERE " + predicate, [stage_name, DEFAULT_LEASE_SECONDS, *params[1:]])
            if result.rowcount != 1:
                raise PipelineError("pipeline lease is no longer held")
            return True

    def finish_stage(self, run_id: str, stage_name: str, *, input_count: int, output_count: int, error_count: int = 0, model_calls: int = 0, token_count: int = 0, cost_estimate: float = 0.0, duration_ms: int = 0, lease_owner: str | None = None) -> None:
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_stages SET status = 'COMPLETE', input_count = %s, output_count = %s, error_count = %s, model_calls = %s, token_count = %s, cost_estimate = %s, duration_ms = %s, completed_at = now() WHERE run_id = %s AND stage_name = %s", (input_count, output_count, error_count, model_calls, token_count, cost_estimate, duration_ms, run_id, stage_name))
            self._heartbeat_in_connection(conn, run_id, lease_owner)

    def fail_stage(self, run_id: str, stage_name: str, message: str, *, lease_owner: str | None = None) -> None:
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_stages SET status = 'FAILED', error_count = error_count + 1, error = %s, completed_at = now() WHERE run_id = %s AND stage_name = %s", (message[:1000], run_id, stage_name))
            conn.execute("UPDATE pipeline_runs SET status = 'FAILED', error = %s, lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = now(), updated_at = now() WHERE run_id = %s", (message[:1000], run_id))
            self._event(conn, run_id, "FAILED", lease_owner, detail={"stage": stage_name, "error": _redact(message)})

    def complete_run(self, run_id: str, status: str, *, lease_owner: str | None = None) -> None:
        if status not in {"SUCCEEDED", "EMPTY"}:
            raise PipelineError("invalid terminal pipeline status")
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_runs SET status = %s, current_stage = NULL, lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = now(), updated_at = now() WHERE run_id = %s", (status, run_id))
            self._event(conn, run_id, "COMPLETED", lease_owner, detail={"status": status})

    def set_report_context(self, run_id: str, context: dict[str, Any]) -> None:
        """Persist compact operational facts so every read surface sees one report."""
        with connection(self.database_url) as conn:
            conn.execute(
                "UPDATE pipeline_runs SET report_metadata = COALESCE(report_metadata, '{}'::jsonb) || %s, updated_at = now() WHERE run_id = %s",
                (Jsonb(_redact(context)), run_id),
            )

    @staticmethod
    def _heartbeat_in_connection(conn, run_id: str, lease_owner: str | None) -> None:
        clauses = ["run_id = %s", "status = 'RUNNING'"]
        params: list[Any] = [DEFAULT_LEASE_SECONDS, run_id]
        if lease_owner:
            clauses.append("lease_owner = %s")
            params.append(lease_owner)
        conn.execute("UPDATE pipeline_runs SET heartbeat_at = now(), lease_expires_at = now() + (%s * interval '1 second'), updated_at = now() WHERE " + " AND ".join(clauses), params)

    def report(self, run_id: str) -> dict[str, Any]:
        with connection(self.database_url) as conn:
            run = conn.execute("SELECT run_id, run_date, policy_version, status, current_stage, error, created_at, updated_at, mode, lease_owner, lease_expires_at, heartbeat_at, recovery_count, report_metadata FROM pipeline_runs WHERE run_id = %s", (run_id,)).fetchone()
            if run is None:
                raise PipelineError("pipeline run not found")
            stages = conn.execute("SELECT stage_name, status, attempt_count, input_count, output_count, error_count, policy_version, duration_ms, model_calls, token_count, cost_estimate, error, started_at, completed_at FROM pipeline_stages WHERE run_id = %s ORDER BY array_position(%s::text[], stage_name)", (run_id, list(STAGES))).fetchall()
            events = conn.execute("SELECT event_type, prior_lease_owner, lease_owner, detail, created_at FROM pipeline_run_events WHERE run_id = %s ORDER BY event_id", (run_id,)).fetchall()
        metadata = dict(run[13] or {})
        result = {
            "run_id": str(run[0]), "run_date": run[1].isoformat(), "policy_version": str(run[2]), "status": str(run[3]),
            "current_stage": run[4], "error": _redact(run[5]), "created_at": run[6].isoformat(), "updated_at": run[7].isoformat(),
            "mode": str(run[8]), "lease": {"active": bool(run[9]), "expires_at": run[10].isoformat() if run[10] else None, "heartbeat_at": run[11].isoformat() if run[11] else None, "recovery_count": int(run[12])},
            "stages": [{"stage_name": str(item[0]), "status": str(item[1]), "attempt_count": int(item[2]), "input_count": int(item[3]), "output_count": int(item[4]), "error_count": int(item[5]), "policy_version": str(item[6]), "duration_ms": int(item[7]), "model_calls": int(item[8]), "token_count": int(item[9]), "cost_estimate": float(item[10]), "error": _redact(item[11]), "started_at": item[12].isoformat() if item[12] else None, "completed_at": item[13].isoformat() if item[13] else None} for item in stages],
            "events": [{"event_type": str(item[0]), "prior_lease_owner": item[1], "lease_owner": item[2], "detail": _redact(dict(item[3] or {})), "created_at": item[4].isoformat()} for item in events],
            **_redact(metadata),
        }
        result["outcome_classification"] = _classification(result)
        result["remediation"] = _remediation(result["outcome_classification"], result)
        return result

    def readiness(self) -> dict[str, Any]:
        """Return source readiness without fetching, enabling, or mutating sources."""
        with connection(self.database_url) as conn:
            rows = conn.execute(
                """SELECT s.source_id, s.source_type, s.name, c.enabled, COALESCE(s.data_origin, 'UNCLASSIFIED'),
                          c.metadata, latest.status, latest.finished_at,
                          COALESCE(latest.stored_count, 0), COALESCE(latest.failure_count, 0)
                   FROM sources s JOIN ingestion_source_configs c ON c.source_id = s.source_id
                   LEFT JOIN LATERAL (
                       SELECT cr.status, cr.finished_at,
                              count(*) FILTER (WHERE cir.outcome = 'STORED') AS stored_count,
                              count(*) FILTER (WHERE cir.outcome IN ('FAILED_TRANSIENT', 'FAILED_PERMANENT')) AS failure_count
                       FROM collection_runs cr LEFT JOIN collection_item_results cir ON cir.run_id = cr.run_id
                       WHERE cr.source_ids ? s.source_id
                       GROUP BY cr.run_id ORDER BY cr.started_at DESC LIMIT 1
                   ) latest ON TRUE ORDER BY s.source_type, s.name"""
            ).fetchall()
        sources = []
        for row in rows:
            metadata = dict(row[5] or {})
            if not bool(row[3]):
                state, remediation = "DISABLED", "Enable only after explicit source review."
            elif str(row[4]) in {"FIXTURE", "TEST"}:
                state, remediation = "FIXTURE_ONLY", "Configure a reviewed LIVE source before live publication."
            elif str(metadata.get("review_status", "")).upper() in {"PENDING", "PENDING_REVIEW"}:
                state, remediation = "PENDING_REVIEW", "Complete source review before enabling collection."
            elif row[6] is None:
                state, remediation = "NEVER_COLLECTED", "Run an explicit live collection after checking the source endpoint."
            elif str(row[6]) == "FAILED":
                state, remediation = "FAILED", "Inspect the latest collection error and retry only after correcting the source issue."
            elif int(row[7] or 0) == 0:
                state, remediation = "EMPTY", "The source is reachable but yielded no new items; check again on its normal cadence."
            else:
                state, remediation = "USABLE", "Ready for bounded collection."
            sources.append({"source_id": str(row[0]), "source_type": str(row[1]), "name": str(row[2]), "state": state, "latest_collection_status": row[6], "latest_finished_at": row[7].isoformat() if row[7] else None, "stored_count": int(row[8]), "failure_count": int(row[9]), "remediation": remediation})
        usable = sum(1 for item in sources if item["state"] == "USABLE")
        return {"status": "READY" if usable else "READINESS_FAILURE", "usable_source_count": usable, "sources": sources, "remediation": "At least one reviewed LIVE source is usable." if not usable else "Run the worker in an explicit mode."}


_SENSITIVE_KEY = re.compile(r"(?:password|secret|token|authorization|api[_-]?key)", re.IGNORECASE)
_URL_CREDENTIALS = re.compile(r"(postgres(?:ql)?://[^:/@]+:)[^@/]+@", re.IGNORECASE)


def _redact(value: Any) -> Any:
    """Remove credentials while preserving enough operational context to debug."""
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    return value


def _classification(report: dict[str, Any]) -> str:
    events = {item["event_type"] for item in report.get("events", [])}
    if any(item.startswith("NOOP_") for item in events) and report.get("status") in TERMINAL_STATUSES | {"RUNNING", "FAILED"}:
        return "NOOP"
    if report.get("status") == "FAILED":
        return "FAILED"
    if "STALE_RECLAIMED" in events and report.get("status") in TERMINAL_STATUSES:
        return "STALE_RECOVERED"
    outcomes = report.get("source_outcomes", [])
    if outcomes and any(item.get("status") in {"FAILED", "PARTIAL"} or int(item.get("failed_transient", 0)) + int(item.get("failed_permanent", 0)) > 0 for item in outcomes):
        return "PARTIAL"
    if report.get("mode") == "fixture":
        return "FIXTURE_ONLY"
    if report.get("status") == "EMPTY":
        return "EMPTY"
    if report.get("status") == "SUCCEEDED":
        return "SUCCEEDED"
    return "NOOP" if report.get("status") == "RUNNING" else "FAILED"


def _remediation(classification: str, report: dict[str, Any]) -> str:
    messages = {
        "SUCCEEDED": "No action required; inspect evidence and Riffs before acting on the result.",
        "EMPTY": "This is a valid empty run; wait for new independent evidence or inspect source readiness.",
        "PARTIAL": "Inspect source outcomes, correct only the failed source, then run a bounded resume or next scheduled cycle.",
        "FAILED": "Inspect the failed stage and error, correct configuration or source behavior, then resume the run.",
        "STALE_RECOVERED": "Recovery completed; inspect the retained stage history before relying on the result.",
        "NOOP": "Inspect lease and event history; do not start a concurrent worker for the same date and policy.",
        "READINESS_FAILURE": "Run the readiness report and configure or review at least one usable source.",
        "FIXTURE_ONLY": "Fixture output is for testing only; run explicit live collection for real-world intelligence.",
    }
    return messages.get(classification, "Inspect the canonical report before retrying.")


class DailyPipeline:
    def __init__(self, database_url: str, *, max_candidates: int = 20, max_deep_analyses: int = 5, max_riffs: int = 3):
        if not 1 <= max_candidates <= 20 or not 1 <= max_deep_analyses <= 20 or not 1 <= max_riffs <= 3:
            raise PipelineError("invalid pipeline bounds")
        self.database_url = database_url
        self.max_candidates = max_candidates
        self.max_deep_analyses = max_deep_analyses
        self.max_riffs = max_riffs
        self.repository = PipelineRepository(database_url)

    def run(self, fixture_path: str | Path | DailyFixture, *, run_date: date | None = None, policy_version: str | None = None, fail_stage: str | None = None, resume: bool = False) -> dict[str, Any]:
        fixture_hint = load_fixture(fixture_path, run_date=run_date, policy_version=policy_version) if isinstance(fixture_path, (str, Path)) else fixture_path
        if run_date is not None or policy_version is not None:
            from dataclasses import replace

            fixture_hint = replace(fixture_hint, run_date=run_date or fixture_hint.run_date, policy_version=policy_version or fixture_hint.policy_version)
        claim = self.repository.claim(fixture_hint.run_date, fixture_hint.policy_version, resume=resume, mode="fixture")
        run_id, claimed = claim
        if not claimed:
            report = self.repository.report(run_id)
            report.update({"noop": True, "reason": claim.reason})
            return report
        self.repository.set_report_context(run_id, {"origin_counts": {"FIXTURE": len(fixture_hint.receipts)}, "source_outcomes": []})
        fixture: DailyFixture | None = None
        selected = tuple(sorted(fixture_hint.candidates, key=lambda item: (-item.score, item.candidate_id))[: self.max_candidates])
        published_status = "EMPTY"
        for stage in STAGES:
            if not self.repository.begin_stage(run_id, stage, lease_owner=claim.lease_owner):
                continue
            started = time.monotonic()
            try:
                if fail_stage == stage:
                    raise PipelineError(f"injected failure at {stage}")
                if stage == "COLLECT":
                    fixture = fixture_hint
                    counts = (len(fixture.receipts), len(fixture.candidates))
                elif stage == "RECEIPT":
                    if fixture is None:
                        fixture = fixture_hint
                    seed_fixture(self.database_url, fixture)
                    counts = (len(fixture.receipts), len(fixture.receipts))
                elif stage in {"CAPABILITY", "PROFILE"}:
                    if fixture is None:
                        fixture = fixture_hint
                    counts = (len(fixture.candidates), len(fixture.candidates))
                elif stage == "SIGNAL":
                    if fixture is None:
                        fixture = fixture_hint
                    selected = tuple(sorted(fixture.candidates, key=lambda item: (-item.score, item.candidate_id))[: self.max_candidates])
                    counts = (len(fixture.candidates), len(selected))
                elif stage == "RIFF":
                    selected = tuple(selected[: self.max_deep_analyses])
                    counts = (len(selected), len(selected))
                else:
                    if fixture is None:
                        fixture = fixture_hint
                    from dataclasses import replace

                    bounded = replace(fixture, candidates=tuple(selected[: self.max_deep_analyses]))
                    seed_fixture(self.database_url, bounded)
                    result = DailyRiffService(RiffRepository(self.database_url), DeterministicReasoningProvider(), policy_version=bounded.policy_version, max_candidates=self.max_deep_analyses, max_riffs=self.max_riffs).generate(bounded.run_date, bounded.candidates)
                    published_status = "SUCCEEDED" if result.status == "COMPLETED" else "EMPTY"
                    counts = (len(bounded.candidates), len(result.riffs))
                    self.repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], model_calls=result.provider_calls, duration_ms=int((time.monotonic() - started) * 1000), lease_owner=claim.lease_owner)
                    continue
                self.repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], duration_ms=int((time.monotonic() - started) * 1000), lease_owner=claim.lease_owner)
            except Exception as exc:
                self.repository.fail_stage(run_id, stage, str(exc), lease_owner=claim.lease_owner)
                return self.repository.report(run_id)
        self.repository.complete_run(run_id, published_status, lease_owner=claim.lease_owner)
        return self.repository.report(run_id)
