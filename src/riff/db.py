"""Postgres connection and migration primitives."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@contextmanager
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    """Yield a transactional connection and always close it."""

    with psycopg.connect(database_url) as conn:
        yield conn


def database_ready(database_url: str) -> bool:
    """Return whether a simple database query succeeds."""

    try:
        with connection(database_url) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except psycopg.Error:
        return False


def migrate(database_url: str) -> list[str]:
    """Apply each unapplied numbered SQL migration exactly once."""

    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    with connection(database_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row[0].decode() if isinstance(row[0], bytes) else row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        newly_applied: list[str] = []
        for migration_file in migration_files:
            version = migration_file.stem
            if version in applied:
                continue
            conn.execute(migration_file.read_text(encoding="utf-8"))
            result = conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s) "
                "ON CONFLICT (version) DO NOTHING",
                (version,),
            )
            if result.rowcount:
                newly_applied.append(version)
        return newly_applied
