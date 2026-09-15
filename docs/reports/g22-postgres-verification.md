# G22 Postgres verification — 2026-09-14

## Result

`PASS` for the G22 database-backed acceptance path.

## Environment

- Docker Compose service: `riff-postgres-1`
- PostgreSQL server: `16.15`
- Database: local `riff` database on `127.0.0.1:5432`
- Migrations applied: `001_initial` through `015_engineer_rss_metadata`

## Verification

| Check | Result |
|---|---|
| Container readiness | `/var/run/postgresql:5432 - accepting connections` |
| First migration run | `applied: []` |
| Repeated migration run | `applied: []` |
| PostgreSQL-marked suite | `86 passed, 93 deselected, 2 warnings` |
| Offline suite | `93 passed, 86 deselected, 2 warnings` |
| Combined suite | Exit `0` (`179` tests represented by the two runs above) |

Commands used:

```sh
export RIFF_POSTGRES_PASSWORD=riff-local-only
export RIFF_DATABASE_URL=postgresql://riff:riff-local-only@localhost:5432/riff
docker compose up -d postgres
docker compose exec postgres pg_isready -U riff -d riff
.venv/bin/python -m riff migrate
.venv/bin/python -m riff migrate
RIFF_DATABASE_URL=postgresql://riff:riff-local-only@localhost:5432/riff .venv/bin/python -m pytest -m postgres
.venv/bin/python -m pytest -m 'not postgres'
RIFF_DATABASE_URL=postgresql://riff:riff-local-only@localhost:5432/riff .venv/bin/python -m pytest -q
```

The initial full Postgres run exposed a test isolation defect: a URL-intake
assertion selected an arbitrary prior `job_postings` row from the persistent
Docker volume. The test now queries the evidence ID returned by the run's
synthesis receipt. The focused test and complete Postgres suite pass after the
fix.

Two dependency deprecation warnings remain from FastAPI/Starlette/httpx and
AnyIO. They are non-blocking and routed to dependency maintenance rather than
expanded into G22.

## Gap disposition

- Environment blockers: none with Docker Desktop running.
- Correctness defect: stale global-row selection in the URL-intake test was
  corrected to use the returned evidence ID.
- Deferred hardening: FastAPI/Starlette/httpx and AnyIO dependency deprecations.
