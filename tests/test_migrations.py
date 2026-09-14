import os

import pytest

from riff.db import migrate


@pytest.mark.postgres
def test_initial_migration_is_idempotent():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    first_run = migrate(database_url)
    assert set(first_run) <= {"001_initial"}
    assert migrate(database_url) == []
