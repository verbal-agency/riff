# G00 — Establish the executable application foundation

**Status:** Ready  
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

- [ ] A documented clean-start workflow installs dependencies and starts required local infrastructure.
- [ ] The migration command upgrades an empty Postgres database to the current schema and is repeatable without error.
- [ ] The API health check distinguishes application liveness from database readiness.
- [ ] The one-shot worker entry point starts, emits a structured completion event, and exits successfully.
- [ ] Invalid or missing required configuration fails early with an actionable message and no secret values.
- [ ] Unit tests and Postgres integration tests run through documented commands; no test requires internet or paid credentials.
- [ ] The project has a single documented full-verification command and it passes.

## Verification evidence

Capture the commands and results for clean database migration, health/readiness behavior, worker execution, and the complete test suite. A mocked health response without a real test-database connection is insufficient.

## Implementation latitude

Luna may choose the Python packaging, API, ORM/query, migration, and command-line libraries. Prefer boring, maintained choices and avoid abstractions whose only justification is hypothetical multi-user or multi-service scale.
