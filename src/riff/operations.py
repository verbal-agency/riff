"""Durable, bounded orchestration for the daily Riff funnel (G13)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .db import connection
from .daily import DailyFixture, load_fixture, seed_fixture
from .riffs import DailyRiffService, DeterministicReasoningProvider, RiffRepository


STAGES = ("COLLECT", "RECEIPT", "CAPABILITY", "PROFILE", "SIGNAL", "RIFF", "PUBLISH")
TERMINAL_STATUSES = {"SUCCEEDED", "EMPTY"}


class PipelineError(ValueError):
    """A bounded pipeline request or persisted run error."""


class PipelineRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def claim(self, run_date: date, policy_version: str, *, resume: bool = False) -> tuple[str, bool]:
        with connection(self.database_url) as conn:
            run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"riff-pipeline:{run_date.isoformat()}:{policy_version}"))
            inserted = conn.execute("INSERT INTO pipeline_runs (run_id, run_date, policy_version, status) VALUES (%s, %s, %s, 'RUNNING') ON CONFLICT (run_date, policy_version) DO NOTHING", (run_id, run_date, policy_version)).rowcount == 1
            row = conn.execute("SELECT run_id, status FROM pipeline_runs WHERE run_date = %s AND policy_version = %s FOR UPDATE", (run_date, policy_version)).fetchone()
            if row is None:
                raise PipelineError("pipeline run could not be claimed")
            existing_id, current = str(row[0]), str(row[1])
            if current in TERMINAL_STATUSES:
                return existing_id, False
            if current == "RUNNING" and not resume and not inserted:
                return existing_id, False
            conn.execute("UPDATE pipeline_runs SET status = 'RUNNING', error = NULL, updated_at = now() WHERE run_id = %s", (existing_id,))
            for stage in STAGES:
                conn.execute("INSERT INTO pipeline_stages (stage_id, run_id, stage_name, status, policy_version) VALUES (%s, %s, %s, 'PENDING', %s) ON CONFLICT (run_id, stage_name) DO NOTHING", (str(uuid.uuid5(uuid.NAMESPACE_URL, f"{existing_id}:{stage}")), existing_id, stage, policy_version))
            return existing_id, True

    def begin_stage(self, run_id: str, stage_name: str) -> bool:
        with connection(self.database_url) as conn:
            row = conn.execute("SELECT status FROM pipeline_stages WHERE run_id = %s AND stage_name = %s FOR UPDATE", (run_id, stage_name)).fetchone()
            if row is None:
                raise PipelineError(f"unknown pipeline stage: {stage_name}")
            if str(row[0]) == "COMPLETE":
                return False
            conn.execute("UPDATE pipeline_stages SET status = 'RUNNING', attempt_count = attempt_count + 1, started_at = now(), error = NULL WHERE run_id = %s AND stage_name = %s", (run_id, stage_name))
            conn.execute("UPDATE pipeline_runs SET current_stage = %s, updated_at = now() WHERE run_id = %s", (stage_name, run_id))
            return True

    def finish_stage(self, run_id: str, stage_name: str, *, input_count: int, output_count: int, error_count: int = 0, model_calls: int = 0, token_count: int = 0, cost_estimate: float = 0.0, duration_ms: int = 0) -> None:
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_stages SET status = 'COMPLETE', input_count = %s, output_count = %s, error_count = %s, model_calls = %s, token_count = %s, cost_estimate = %s, duration_ms = %s, completed_at = now() WHERE run_id = %s AND stage_name = %s", (input_count, output_count, error_count, model_calls, token_count, cost_estimate, duration_ms, run_id, stage_name))

    def fail_stage(self, run_id: str, stage_name: str, message: str) -> None:
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_stages SET status = 'FAILED', error_count = error_count + 1, error = %s, completed_at = now() WHERE run_id = %s AND stage_name = %s", (message[:1000], run_id, stage_name))
            conn.execute("UPDATE pipeline_runs SET status = 'FAILED', error = %s, updated_at = now() WHERE run_id = %s", (message[:1000], run_id))

    def complete_run(self, run_id: str, status: str) -> None:
        if status not in {"SUCCEEDED", "EMPTY"}:
            raise PipelineError("invalid terminal pipeline status")
        with connection(self.database_url) as conn:
            conn.execute("UPDATE pipeline_runs SET status = %s, current_stage = NULL, updated_at = now() WHERE run_id = %s", (status, run_id))

    def report(self, run_id: str) -> dict[str, Any]:
        with connection(self.database_url) as conn:
            run = conn.execute("SELECT run_id, run_date, policy_version, status, current_stage, error, created_at, updated_at FROM pipeline_runs WHERE run_id = %s", (run_id,)).fetchone()
            if run is None:
                raise PipelineError("pipeline run not found")
            stages = conn.execute("SELECT stage_name, status, attempt_count, input_count, output_count, error_count, policy_version, duration_ms, model_calls, token_count, cost_estimate, error, started_at, completed_at FROM pipeline_stages WHERE run_id = %s ORDER BY array_position(%s::text[], stage_name)", (run_id, list(STAGES))).fetchall()
        return {"run_id": str(run[0]), "run_date": run[1].isoformat(), "policy_version": str(run[2]), "status": str(run[3]), "current_stage": run[4], "error": run[5], "created_at": run[6].isoformat(), "updated_at": run[7].isoformat(), "stages": [{"stage_name": str(item[0]), "status": str(item[1]), "attempt_count": int(item[2]), "input_count": int(item[3]), "output_count": int(item[4]), "error_count": int(item[5]), "policy_version": str(item[6]), "duration_ms": int(item[7]), "model_calls": int(item[8]), "token_count": int(item[9]), "cost_estimate": float(item[10]), "error": item[11], "started_at": item[12].isoformat() if item[12] else None, "completed_at": item[13].isoformat() if item[13] else None} for item in stages]}


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
        run_id, claimed = self.repository.claim(fixture_hint.run_date, fixture_hint.policy_version, resume=resume)
        if not claimed:
            report = self.repository.report(run_id)
            report["noop"] = True
            report["reason"] = "already_running_or_terminal"
            return report
        fixture: DailyFixture | None = None
        selected = tuple(sorted(fixture_hint.candidates, key=lambda item: (-item.score, item.candidate_id))[: self.max_candidates])
        published_status = "EMPTY"
        for stage in STAGES:
            if not self.repository.begin_stage(run_id, stage):
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
                    self.repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], model_calls=result.provider_calls, duration_ms=int((time.monotonic() - started) * 1000))
                    continue
                self.repository.finish_stage(run_id, stage, input_count=counts[0], output_count=counts[1], duration_ms=int((time.monotonic() - started) * 1000))
            except Exception as exc:
                self.repository.fail_stage(run_id, stage, str(exc))
                return self.repository.report(run_id)
        self.repository.complete_run(run_id, published_status)
        return self.repository.report(run_id)
