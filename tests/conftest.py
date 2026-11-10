"""Keep Postgres integration tests out of the development database.

Tests read ``RIFF_DATABASE_URL``.  When it is set, this file points it at a
separate database (``RIFF_TEST_DATABASE_URL``, or ``<name>_test`` on the same
server), creating and migrating that database on first use.  It never falls
back to the development database.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from riff.db import migrate


def _test_database_url(dev_url: str) -> str:
    explicit = os.environ.get("RIFF_TEST_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    parts = urlsplit(dev_url)
    name = parts.path.lstrip("/") or "riff"
    return urlunsplit(parts._replace(path=f"/{name if name.endswith('_test') else name + '_test'}"))


def pytest_configure(config: pytest.Config) -> None:
    dev_url = os.environ.get("RIFF_DATABASE_URL", "").strip()
    if not dev_url:
        return
    test_url = _test_database_url(dev_url)
    if test_url != dev_url:
        name = urlsplit(test_url).path.lstrip("/")
        try:
            with psycopg.connect(dev_url, autocommit=True) as conn:
                if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
                    conn.execute(f'CREATE DATABASE "{name}"')
        except psycopg.Error as exc:
            raise pytest.UsageError(f"could not prepare test database {name!r}: {exc}") from exc
    migrate(test_url)
    os.environ["RIFF_DATABASE_URL"] = test_url
