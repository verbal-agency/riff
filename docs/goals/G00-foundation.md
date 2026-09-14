# G00 — Establish the executable application foundation

**Status:** Complete
**Depends on:** None  
**Unlocks:** G01 and every later goal  
**PRD references:** Sections 26–31

## Outcome

Riff exists as one locally runnable Python application with Postgres persistence, migrations, configuration, a test harness, and distinct entry points for API and scheduled-worker responsibilities. The foundation makes later vertical slices easy to verify without prematurely implementing product behavior.

## User-visible proof

From a clean checkout, a contributor can follow the documented setup, initialize the database, start the application, and receive a healthy response that confirms both application and database readiness.

## Inputs

- The Riff v0.1 PRD and this roadmap's cross-goal invariants.
- An empty repository and a locally available Postgres instance/container runtime.

## Scope

- Create the Python package and dependency/project metadata.
- Establish environment-based configuration with a checked-in safe example.
- Connect to Postgres and add a repeatable migration mechanism.
- Provide API and worker entry points within the same application/package.
- Add structured logging and stable application error boundaries.
- Add unit and Postgres-backed integration-test layers.
- Document local setup, verification, migration, API startup, and one-shot worker invocation.
- Add a lightweight architecture note naming the chosen web, database, migration, validation, and test libraries and why they fit v0.1.

## Non-goals

- Evidence, capability, signal, Riff, or profile behavior.
- Authentication, a browser UI, microservices, queues, Kafka, Kubernetes, or a separate vector database.
- Production cloud deployment.
- Selecting a permanent model provider.

## Required properties

- API and worker use the same domain/application layer and database configuration.
- Importing the package has no network, database, or worker side effects.
- Schema changes are migration-driven; application startup does not silently mutate schema.
- Secrets are read from configuration and are never committed or logged.
- The test suite can run without model credentials or paid network calls.

## Deliverables

- Runnable Python application and package metadata.
- Postgres connection and initial migration/version table.
- Health/readiness endpoint or equivalent small API operation.
- One-shot no-op worker command proving worker bootstrapping.
- Automated tests and contributor documentation.
- Architecture decision record for the foundational library choices.

## Acceptance criteria

- [x] A documented clean-start workflow installs dependencies and starts required local infrastructure.
- [x] The migration command upgrades an empty Postgres database to the current schema and is repeatable without error.
- [x] The API health check distinguishes application liveness from database readiness.
- [x] The one-shot worker entry point starts, emits a structured completion event, and exits successfully.
- [x] Invalid or missing required configuration fails early with an actionable message and no secret values.
- [x] Unit tests and Postgres integration tests run through documented commands; no test requires internet or paid credentials.
- [x] The project has a single documented full-verification command and it passes.

## Verification evidence

Capture the commands and results for clean database migration, health/readiness behavior, worker execution, and the complete test suite. A mocked health response without a real test-database connection is insufficient.

## Cycle verification (2026-09-14)

- `uv sync --all-groups` resolved and installed the locked application/test dependencies.
- `.venv/bin/python -m pytest` → **8 passed, 1 skipped** (the skip is the opt-in Postgres marker when no database URL is set).
- Against an isolated temporary PostgreSQL 14 instance: `.venv/bin/python -m riff migrate` applied `001_initial`; `.venv/bin/python -m pytest -m postgres` → **1 passed**; a second migration call was a no-op.
- Against that same live database, `GET /health/live` returned 200 without a database query and `GET /health/ready` returned 200 with `{"status":"ok","database":"ready"}`. The unavailable path is covered by `tests/test_api.py` and returns 503.
- `RIFF_DATABASE_URL=postgresql://user:secret@localhost:5432/riff .venv/bin/riff worker` emitted one JSON `worker.completed` event, exited 0, and did not emit the password.
- `.venv/bin/python -m compileall -q src tests` and `git diff --check` passed.

## Implementation latitude

Luna may choose the Python packaging, API, ORM/query, migration, and command-line libraries. Prefer boring, maintained choices and avoid abstractions whose only justification is hypothetical multi-user or multi-service scale.
