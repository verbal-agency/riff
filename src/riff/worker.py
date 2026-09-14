"""Scheduled-worker entry point. Domain stages arrive in later goals."""

from __future__ import annotations

import logging
import uuid

from .config import Settings
from .logging import configure_logging, event


def run_worker(settings: Settings | None = None) -> str:
    """Run the foundation no-op worker and return its run identifier."""

    effective = settings or Settings.from_env()
    configure_logging(effective.log_level)
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

