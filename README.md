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

### Engineer-authored RSS selection

The G17 roster is separate from collection approval. Review the per-source
selection manifest before projecting any engineer feed into the technical
writing registries:

```sh
uv run riff source engineer-rss validate
uv run riff source engineer-rss preview
uv run riff source engineer-rss project --selection-id <selection-id>
uv run riff source engineer-rss project --selection-id <selection-id> --apply
uv run riff source sync --registry config/technical_sources.json
```

Only a selection with `collection_decision=ENABLE`, confirmed permission, a
reviewer, and a review date can be projected. The manifest is fail-closed and
all roster selections remain disabled until these per-source terms and
retention decisions are recorded. Engineer identity, ownership, organization,
and correlation metadata are carried into RSS retrieval metadata.

## GitHub collection

Configure one explicit repository per `GITHUB` source in
`config/github_sources.json`, using its API scope as
the endpoint (for example, `https://api.github.com/repos/owner/repository`).
Set `GITHUB_TOKEN` only in the process environment when private or higher-rate
limit access is required; the token is never stored in the source registry or
collection state. Then run `uv run riff ingest --source-type GITHUB`.

The adapter is read-only and bounded: it collects repository metadata, releases,
issues, and README snapshots, paginates at a configured page limit, and keeps
repository IDs stable across renames/transfers. Bodies larger than the bound
are truncated with the canonical GitHub URL retained as `snapshot_ref`. Stars
and fork counts remain weak metadata and are not treated as trend evidence.

Automated tests use recorded responses under `tests/fixtures/github/`; no live
GitHub request is made by the test suite. A live credential smoke run is an
explicit operator action, not part of normal verification.

### Bounded GitHub discovery

G20 keeps discovery separate from collection. Review the disabled-by-default
policy in `config/github_discovery.json`, then run the recorded search fixture:

```sh
uv run riff github discover \
  --policy config/github_discovery.json \
  --fixture tests/fixtures/github/discovery/search-responses-v1.json \
  --output /tmp/riff-github-queue.json
uv run riff github queue --file /tmp/riff-github-queue.json
uv run riff github review --file /tmp/riff-github-queue.json --candidate-id repo:5001 --apply
uv run riff github promote --queue /tmp/riff-github-queue.json \
  --candidate-id repo:5001 --confirm PROMOTE --apply
```

Promotion writes a disabled, provenance-bearing scope to
`config/github_sources.json`; it never enables or collects a repository by
itself. The live path requires `--live`, an enabled reviewed policy, and uses
the existing bounded read-only GitHub REST client. Tests use recorded responses
only and filter forks, mirrors, bots, duplicate aliases, and popularity-only
matches.

## Job-market import

G04 uses a permitted, offline-first JSON import seam rather than scraping a job
site. Configure a bounded `JOBS` source in `config/job_sources.json`, obtain a
compliant export, and import it with:

```sh
uv run riff job import --source-id <source-id> --file tests/fixtures/jobs/initial.json
```

The import format is schema version 1 and keeps employer identity separate from
posting evidence. Exact reposts create another retrieval without a duplicate
evidence version; changed descriptions create a `VERSION_OF` chain. Missing
compensation, seniority, and dates remain unknown, and expired postings are
retained. Fixtures under `tests/fixtures/jobs/` are the normal development and
evaluation path and require no credentials or network access.

## Evidence Receipts

G05 turns stored evidence into compact, validated receipts for downstream
normalization. Processing is cache-keyed by evidence content hash and extractor
version, and grounded spans retain exact offsets back to the raw evidence:

```sh
uv run riff receipt process --limit 100
uv run riff receipt process --evidence-id <evidence-id> --force
uv run riff receipt evaluate --file tests/fixtures/receipts/labeled.json
```

The default `keyword-v1` extractor is deterministic and offline. A structured
provider can be injected behind the same extractor interface later. Failed
validation and transient attempts are retained for inspection and retry; a
receipt read returns compact fields and does not load the raw body.

## Capability normalization

G06 normalizes receipt candidates into separate, reversible capability and
technology records. Deterministic aliases group bounded synonyms such as
checkpoint recovery, resumable agents, and workflow replay under durable
execution while preserving the original candidate and receipt provenance:

```sh
uv run riff capability normalize --limit 100
uv run riff capability inspect --capability-id <capability-id>
uv run riff capability review accept --mapping-id <mapping-id> --reason "confirmed"
uv run riff capability evaluate --file tests/fixtures/capabilities/normalization.json
```

Review decisions are append-only and support accept, reject, remap, split, and
undo. Technology relationships are many-to-many; low-confidence mappings remain
proposed and never silently alter canonical capability counts.

## User capability profile

G07 adds capability-scoped public evidence and a private, user-attested
Experience Ledger. Gap assessments distinguish signaling, implementation,
experience, and knowledge gaps without treating GitHub absence as proof:

```sh
uv run riff profile ledger add --capability-id <capability-id> --entry "Led durable workflow delivery" --employer-or-context "client work"
uv run riff profile assess --capability-id <capability-id>
uv run riff profile view --capability-id <capability-id> --public
uv run riff profile evaluate --file tests/fixtures/profile/gap_cases.json
```

Public views exclude private descriptions and ledger entries. Corrections and
archives are recorded in profile history, and completed Riff artifacts remain
unknown candidate evidence until explicitly assessed.

## Candidate signals

G08 ranks capability-based weak signals with separate explanations for recency,
change, source diversity, independence, novelty, relevance, volume, and profile
adjustment. Correlated reposts, single-employer bursts, established steady
volume, and one-source-type candidates are explicitly penalized or labeled
insufficient:

```sh
uv run riff signal evaluate --file tests/fixtures/signals/adversarial.json
```

Rank runs are versioned and fingerprinted so identical inputs are idempotent;
stored correlation groups and explanations make each ordering inspectable.

## Daily Riffs

G09 turns the strongest bounded candidate set into zero to three structured,
evidence-backed arguments. The provider is replaceable and the default fake is
deterministic, so local evaluation needs no paid model or network:

```sh
uv run riff riff evaluate --file tests/fixtures/riffs/golden.json
```

After evidence, receipts, capabilities, profile, and signals are present, the
persisted daily result is available at `GET /riffs/daily/YYYY-MM-DD`. Published
Riffs retain supporting and counter-receipt IDs; invalid or snapshot-only
citations are rejected, and an empty day is reported honestly.

For a local database-backed smoke run, apply migrations and invoke the
deterministic fixture path twice:

```sh
uv run riff migrate
uv run riff daily generate --file tests/fixtures/riffs/daily_inputs.json
uv run riff daily generate --file tests/fixtures/riffs/daily_inputs.json
```

The second invocation reports `cached: true` and reuses the same daily run.

The complete durable funnel uses the same one-shot worker path and can be
scheduled with a simple cron entry:

```sh
uv run riff migrate
uv run riff worker --fixture tests/fixtures/riffs/daily_inputs.json --resume
# Example: 05:00 every day
5 0 * * * cd /path/to/riff && uv run riff worker --fixture tests/fixtures/riffs/daily_inputs.json --resume
```

Inspect a run with `GET /operations/{run_id}`. Reports distinguish `FAILED`
from a valid `EMPTY` day and include per-stage counts, attempts, timings, and
provider usage.

The stateless conversational adapter exposes a documented `riff-tools-v1`
catalog at `GET /adapter/tools` and dispatches calls through
`POST /adapter/tools/{tool_name}`. It can be exercised locally with the same
`riff api` process and deterministic fixture data; promotion calls require the
explicit `USER_CONFIRMED` token as well as their persisted user approval.

The G15 dogfood packet is fixture-only and replayable: use
`tests/fixtures/dogfood/manifest.json` and inspect
`docs/reports/g15-dogfood-report.json` plus the recorded review in
`docs/reports/g15-human-review.md`. The v0.1 recommendation is `PASS`; follow-up
product input is tracked in `docs/backlog.md`.

The reviewed concrete source plan is validated without a database or network:

```sh
uv run riff source validate-manifest --manifest config/ingestion_sources.json
```

G10 exposes investigation and explicit decision operations through the API:
`GET /riffs/{riff_id}/investigation` and
`POST /riffs/{riff_id}/decisions`. Only a user-originated
`APPROVE_EXPLORATION` decision can move a Riff toward exploration; rejected
Riffs resurface only when new evidence is recorded as a material change.

After a user records `APPROVE_EXPLORATION`, the bounded Exploration lifecycle
is available through `POST /riffs/{riff_id}/explorations`,
`GET /explorations/{exploration_id}`, and the user-only refinement and
selection operations at `/explorations/{exploration_id}/refine` and
`/explorations/{exploration_id}/select`. Selecting an experiment stops before
PRD creation; G12 owns that separate approval boundary.

For a selected Exploration experiment, the distinct PRD approval and project
surfaces are `POST /explorations/{exploration_id}/prd-approvals`,
`POST /explorations/{exploration_id}/prd`, `GET /projects/{project_id}`, and
`GET /projects/{project_id}/markdown`.

Stop local infrastructure with `docker compose down`. The named Postgres volume is local runtime state and is ignored by Git.
