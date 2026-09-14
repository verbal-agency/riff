# Riff

Riff is a personal capability-intelligence system for finding emerging applied-AI capabilities, reasoning about their significance, and turning worthwhile ideas into completed evidence.

The product requirements are in [Riff v0.1 Product Requirements Document.md](Riff%20v0.1%20Product%20Requirements%20Document.md). The implementation roadmap for 5.6 Luna is in [docs/goals/README.md](docs/goals/README.md).

## G00 local setup

Requirements: Python 3.10+, `uv`, Docker Desktop (or a local Postgres 14+ instance).

```sh
uv sync --all-groups
cp .env.example .env
docker compose up -d postgres
uv run riff migrate
uv run riff worker
uv run uvicorn riff.api:app --reload
```

The API exposes:

- `GET /health/live` — process liveness; no database connection.
- `GET /health/ready` — database readiness; returns HTTP 503 until Postgres is reachable.

## Curated writing collection

Edit [config/technical_sources.json](config/technical_sources.json) to add permitted RSS/Atom sources, then sync and collect them without changing application code:

```sh
uv run riff source sync --registry config/technical_sources.json
uv run riff ingest --source-type TECHNICAL_WRITING
```

For a one-off source, use `uv run riff source add --name ... --endpoint ...`. Disable or re-enable it with `uv run riff source disable --source-id ...` and `uv run riff source enable --source-id ...`. Collection is incremental: cursors and per-item outcomes are stored in Postgres, and a run can be retried safely.

For a no-server check, run `.venv/bin/python -m pytest`. Postgres integration checks use the `postgres` marker and are run with:

```sh
RIFF_DATABASE_URL=postgresql://riff:riff@localhost:5432/riff .venv/bin/python -m pytest -m postgres
```

The full verification command is:

```sh
.venv/bin/python -m pytest
```

Stop local infrastructure with `docker compose down`. The named Postgres volume is local runtime state and is ignored by Git.
