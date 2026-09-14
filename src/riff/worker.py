"""Scheduled-worker entry point. Domain stages arrive in later goals."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path

from .config import Settings
from .logging import configure_logging, event


def run_worker(settings: Settings | None = None, *, fixture_path: str | Path | None = None, run_date: date | None = None, policy_version: str | None = None, resume: bool = False) -> str:
    """Run one daily pipeline cycle, retaining the foundation event when no fixture is supplied."""

    effective = settings or Settings.from_env()
    configure_logging(effective.log_level)
    if fixture_path is not None:
        from .operations import DailyPipeline

        report = DailyPipeline(effective.database_url).run(fixture_path, run_date=run_date, policy_version=policy_version, resume=resume)
        event(logging.getLogger("riff.worker"), "worker.completed", **report)
        return report["run_id"]
    run_id = str(uuid.uuid4())
    event(
        logging.getLogger("riff.worker"),
        "worker.completed",
        run_id=run_id,
        status="success",
        environment=effective.environment,
        stages=[] ,
    )
    return run_id
