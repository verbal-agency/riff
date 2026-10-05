import pytest

from riff.config import Settings
from riff.worker import WorkerConfigurationError, run_worker


def test_worker_requires_an_explicit_mode():
    settings = Settings("postgresql://user:password@localhost:5432/riff", environment="test")
    with pytest.raises(WorkerConfigurationError, match="requires --fixture.*--live"):
        run_worker(settings)


def test_worker_rejects_ambiguous_modes():
    settings = Settings("postgresql://user:password@localhost:5432/riff", environment="test")
    with pytest.raises(WorkerConfigurationError, match="exactly one of --fixture, --live, or --replay-live"):
        run_worker(settings, fixture_path="tests/fixtures/riffs/daily_inputs.json", live=True)
