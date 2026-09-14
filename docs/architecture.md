# Riff v0.1 foundation architecture

G00 establishes one Python application with three process entry points: the HTTP API, a one-shot scheduled worker, and a migration command. Later goals add domain behavior behind these seams; this goal deliberately creates no evidence or capability tables.

## Choices

- **Python package:** `src/riff` with `pyproject.toml` and Hatchling metadata. This keeps imports explicit and supports normal editable installs.
- **HTTP API:** FastAPI. It provides typed, small endpoints and a straightforward interface boundary for the future ChatGPT adapter.
- **Database driver:** `psycopg` 3. The application uses direct parameterized SQL for the small foundation and can introduce a repository abstraction as domain tables arrive.
- **Migrations:** numbered SQL files applied by the in-process migration runner. Migrations are explicit and transactional; application startup never mutates schema.
- **Validation/configuration:** standard-library dataclasses and URL validation for the foundation. Domain schemas can add a validation library when G01 requirements justify it.
- **Tests:** pytest with HTTPX for API tests. Postgres tests are separately marked and require an explicitly configured database URL.
- **Scheduling:** an external simple scheduler (cron, launchd, or equivalent) invokes the tested one-shot worker. No queue or workflow service is needed in v0.1.

## Boundaries

Imports have no network or database side effects. Configuration is loaded at command/request boundaries. The API owns health behavior, the worker owns orchestration entry, and the migration command owns schema changes. Secrets are accepted only through environment configuration and are never emitted by structured logs.

## G02 ingestion

Technical-writing sources are a manually editable JSON registry synchronized into Postgres source configuration. The first adapter is RSS/Atom over an injectable HTTP boundary. A one-shot runner records each collection run and item result, writes evidence through the G01 repository, and advances a source cursor only after that evidence transaction commits. Network failures are classified as transient or permanent; malformed entries are quarantined while valid siblings continue. Hacker News discovery is not enabled in this slice.
