"""Explicit fixture and live entry points for the scheduled worker."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from .config import Settings
from .logging import configure_logging, event


class WorkerConfigurationError(ValueError):
    """The worker was invoked without an explicit execution mode."""


def run_worker(
    settings: Settings | None = None,
    *,
    fixture_path: str | Path | None = None,
    live: bool = False,
    replay_live: bool = False,
    run_date: date | None = None,
    policy_version: str | None = None,
    replay_since=None,
    replay_limit: int = 100,
    job_source_id: str | None = None,
    resume: bool = False,
    emit_event: bool = True,
) -> dict[str, Any]:
    """Run one explicit fixture replay or live daily cycle.

    Network collection is never inferred from the absence of a fixture.  The
    caller must pass ``live=True``.
    """

    modes = sum(item is not None for item in (fixture_path, True if live else None, True if replay_live else None))
    if modes > 1:
        raise WorkerConfigurationError("choose exactly one of --fixture, --live, or --replay-live")
    if modes == 0:
        raise WorkerConfigurationError("worker requires --fixture for offline replay, --live for approved source collection, or --replay-live for stored LIVE evidence")
    if replay_limit < 1 or replay_limit > 500:
        raise WorkerConfigurationError("--limit must be between 1 and 500 for --replay-live")

    effective = settings or Settings.from_env()
    configure_logging(effective.log_level)
    if fixture_path is not None:
        from .operations import DailyPipeline

        report = DailyPipeline(effective.database_url).run(fixture_path, run_date=run_date, policy_version=policy_version, resume=resume)
        report = {**report, "mode": "fixture"}
    elif live:
        from .live_worker import run_live_pipeline

        effective_date = run_date or date.today()
        report = run_live_pipeline(
            effective.database_url,
            run_date=effective_date,
            policy_version=policy_version or "riff-live-v1",
            resume=resume,
            job_source_id=job_source_id,
        )
        report = {**report, "mode": "live"}
    else:
        from .live_worker import _live_evidence_ids, run_live_pipeline

        effective_date = run_date or date.today()
        evidence_ids = tuple(_live_evidence_ids(effective.database_url, since=replay_since, limit=replay_limit))
        report = run_live_pipeline(
            effective.database_url,
            run_date=effective_date,
            policy_version=policy_version or "riff-live-replay-v1",
            resume=resume,
            replay_evidence_ids=evidence_ids,
            replay_since=replay_since,
        )
        report = {**report, "mode": "live-replay"}
    if emit_event:
        event(logging.getLogger("riff.worker"), "worker.completed", **report)
    return report
