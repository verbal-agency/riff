# G22 — Configure Postgres and verify persistence boundaries

**Status:** Complete
**Depends on:** G00, G04, G21
**Unlocks:** Repeatable database-backed development and confidence in the job-ingestion persistence path
**PRD references:** Sections 8, 21, 27, 33
**Canonical scenario:** `SC-DB-001`

## Outcome

Riff has a reproducible local PostgreSQL workflow and a verified persistence
test path. A clean checkout can start a local database, apply the complete
migration history, run the PostgreSQL-marked suite without silent skips, and
exercise both scheduled job collection and user-submitted URL intake against
real tables. Failures and environment limitations are visible in the test
report rather than being mistaken for passing behavior.

This goal closes the immediate database verification gap. It does not assume
that every future persistence-hardening idea needs a schema change; those
decisions are made from observed test and operational evidence.

## User-visible proof

An operator can:

1. start the documented local Postgres service with a local-only password;
2. run migrations on a clean database and safely repeat the migration command;
3. run the complete `postgres` test marker and see zero database skips;
4. run a fixture-backed job collection and URL submission that persist runs,
   item outcomes, cursors, evidence, employers, and normalized postings; and
5. inspect a concise report showing which database-backed scenarios passed,
   which were intentionally deferred, and which require human/environmental
   action.

## Scope

### 1. Reproducible local database setup

- Verify `docker-compose.yml` and `.env.example` provide a safe local Postgres
  workflow with no committed real credentials.
- Document one-line commands for starting Postgres, checking readiness, running
  migrations, and running the database tests.
- Keep the database URL explicit through `RIFF_DATABASE_URL`; do not add a
  hidden application default or auto-migrate on startup.
- Provide a clean-database test procedure that does not destroy an operator's
  persistent development volume without an explicit opt-in.

### 2. Migration and schema verification

- Apply every numbered migration in order on a clean database and verify the
  migration runner is idempotent on a second invocation.
- Verify foreign keys, uniqueness constraints, status checks, and transaction
  rollback behavior for the evidence, ingestion, job, receipt, capability,
  profile, signal, daily Riff, decision, exploration, PRD, and pipeline tables.
- Record the applied migration versions and database/server version in the
  verification report.

### 3. Job persistence coverage

- Run the G21 fixture collection through the real Postgres repositories and
  assert durable `collection_runs`, `collection_item_results`, cursors,
  `source_items`, `evidence_versions`, `retrievals`, `job_employers`, and
  `job_postings` records.
- Verify exact replay creates retrieval/run history without a second logical
  evidence version, while changed content creates a `VERSION_OF` chain.
- Run URL intake against the recorded JSON-LD and HTML-fallback fixtures and
  assert raw snapshot retention, normalized fields, parser/policy metadata,
  employer identity, and synthesis-ready evidence IDs.
- Exercise transient and permanent failures, malformed listings, cursor
  non-advancement, and concurrent same-source contention against the database
  path where applicable.

### 4. Cross-domain regression suite

- Run all existing PostgreSQL-marked tests, not only the G21 tests, including
  migration, evidence, RSS/GitHub/job ingestion, receipts, capability,
  profile, signal, daily operations, decisions, explorations, PRDs, and API
  persistence coverage.
- Ensure test fixtures use an isolated database/schema and leave no dependency
  on live providers, credentials, paid models, or private URLs.
- Produce a dated machine-readable or Markdown verification report that can be
  attached to the goal completion handoff.

### 5. Gap disposition

- Compare observed behavior with the current database-gap inventory.
- If a gap is only a future modeling improvement, record it as a follow-up
  rather than expanding this goal.
- If a gap prevents correctness or reliable inspection, add the smallest
  backward-compatible migration and focused test needed to close it.

## Non-goals

- Production database deployment, backups, replication, or secret management.
- Live job-board, RSS, or GitHub requests.
- A distributed scheduler or multi-host deployment.
- Automatically adding tables for policy snapshots, request-attempt history,
  URL-submission entities, or Postgres leases unless verification demonstrates
  that the current contracts cannot satisfy the acceptance criteria.
- Replacing the existing Postgres repository layer or introducing a second
  database/vector store.

## Acceptance criteria

- [ ] A clean local Postgres instance starts from the documented commands, and
  readiness is explicitly checked before migrations run.
- [ ] The complete migration set applies successfully to a clean database and
  a second migration invocation reports no new migrations.
- [ ] `.venv/bin/python -m pytest -m postgres` executes with no database-related
  skips and passes; the offline suite continues to pass independently.
- [ ] G21 collection and URL-intake persistence tests pass against Postgres,
  including replay/versioning, raw evidence, normalized postings, cursors,
  run/item outcomes, and employer identity.
- [ ] Failure-path tests prove permanent failures do not advance cursors,
  transient failures are recorded/retried according to policy, and malformed
  input does not partially corrupt durable state.
- [ ] Migration, constraint, rollback, and cross-domain regression evidence is
  captured in a dated verification report.
- [ ] README/operator documentation gives copy-pasteable setup, readiness,
  migration, test, cleanup, and troubleshooting commands without exposing
  real credentials.
- [ ] Remaining gaps are explicitly classified as environment blockers,
  correctness defects, or deferred hardening work with a proposed follow-up.

## Verification commands

The goal should leave a tested sequence equivalent to:

```sh
export RIFF_POSTGRES_PASSWORD=riff-local-only
export RIFF_DATABASE_URL=postgresql://riff:riff-local-only@localhost:5432/riff
docker compose up -d postgres
docker compose exec postgres pg_isready -U riff -d riff
uv run riff migrate
.venv/bin/python -m pytest -m postgres
.venv/bin/python -m pytest -q
```

The exact commands may vary by local Postgres installation, but the same
database URL, migration runner, and test marker must be used for the evidence
report.

## Cycle verification

- Docker Compose Postgres readiness: `/var/run/postgresql:5432 - accepting connections`.
- PostgreSQL server: `16.15`.
- Applied migrations: `001_initial` through `015_engineer_rss_metadata` (15 total).
- Repeated migration invocation: `applied: []` on both runs.
- `.venv/bin/python -m pytest -m postgres`: `86 passed, 93 deselected, 2 warnings`.
- `.venv/bin/python -m pytest -m 'not postgres'`: `93 passed, 86 deselected, 2 warnings`.
- One stale global-row assertion in `tests/test_job_collection.py` was fixed to
  query the evidence ID returned by the URL-intake receipt; the focused test and
  complete Postgres suite pass afterward.
- Remaining warnings are FastAPI/Starlette/httpx and AnyIO dependency
  deprecations; they do not affect correctness and are deferred to dependency
  maintenance.

## Handoff

Completion must state the database/server version, applied migrations, exact
test commands and pass/skip counts, the G21 persistence observations, and any
remaining deferred schema-hardening items. A missing Docker daemon or blocked
Postgres service is an incomplete verification result, not a passing test.
