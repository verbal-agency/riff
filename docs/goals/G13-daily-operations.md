# G13 — Operate the complete daily funnel reliably

**Status:** Complete
**Depends on:** G09, G09a, G09b, G10, G11, G12
**Unlocks:** G14, G15  
**PRD references:** Sections 8, 26–29, 33

## Outcome

One scheduled worker run reliably coordinates incremental collection, receipt generation, capability mapping, signal ranking, deep analysis, and daily publication with resumability, bounded model work, useful run diagnostics, and no duplicate effects.

## User-visible proof

An operator can trigger or schedule one daily run, inspect stage-by-stage counts and costs, retry a failed stage without duplicating prior work, and then query that date's zero-to-three Riffs.

## Inputs

- The completed collection, receipt, capability, profile, ranking, and Riff stage interfaces.
- Versioned pipeline policy/budget configuration and deterministic end-to-end fixtures.

## Scope

- Compose completed pipeline stages behind one run/date identity.
- Persist stage state, counts, versions, timing, failures, retry state, model-call/token/cost estimates where available, and final outcome.
- Enforce configurable funnel bounds approximating hundreds of observations, dozens of receipts, about twenty candidates, about five deep analyses, and zero to three Riffs.
- Support one-shot, resume, and safe rerun behavior with a single-worker concurrency guard.
- Add scheduling documentation/configuration for one simple scheduled process.
- Provide structured operator summaries and health/staleness information.
- Define data/version behavior when extractor, ranker, or generation policies change.

## Non-goals

- Real-time events, distributed queues, multiple workers, Kubernetes, a monitoring platform, or auto-scaling.
- Reimplementing stage logic inside the orchestrator.

## Required properties

- Durable stage completion precedes cursor/checkpoint advancement.
- A downstream failure never causes already-complete upstream work to be paid for again on normal resume.
- Concurrent runs for the same logical date/policy do not publish duplicates.
- Limits constrain expensive reasoning independently from raw collection volume.
- Partial results are visible and attributable; failure is not silently reported as “no Riffs.”

## Deliverables

- Persisted pipeline-run/stage model and orchestrator.
- One-shot/resume/rerun commands and concurrency protection.
- Funnel budget configuration and usage accounting.
- Operator status/run report and schedule/runbook documentation.
- End-to-end deterministic fixtures with injected failures at each boundary.

## Acceptance criteria

- [x] A successful fixture run moves evidence through every stage and publishes a queryable zero-to-three daily result.
- [x] Injected failure after any stage can resume from the last durable boundary without duplicate records or repeated completed model calls.
- [x] Two concurrent attempts for the same run identity result in one logical publication and an inspectable loser/no-op outcome.
- [x] Deep analysis and published-Riff caps are enforced independently of input volume.
- [x] Run reports expose per-stage input/output/error counts, versions, durations, and model usage/cost estimates when the provider supplies them.
- [x] A failed pipeline is distinguishable from a valid successful zero-Riff day.
- [x] Policy-version changes create an intentional new processing/run version without corrupting earlier results.
- [x] A documented local scheduler example invokes exactly the same tested one-shot worker path.

## Verification evidence

`tests/test_operations.py` runs the deterministic funnel, retries failures after each of the seven stage boundaries, verifies independent candidate/deep/publication caps, distinguishes failed from empty runs, forks policy versions, and exercises the concurrency guard and operator API. Offline verification: `.venv/bin/python -m pytest -q -m 'not postgres'` (49 passed). Complete PostgreSQL verification: `.venv/bin/python -m pytest -q -m postgres` (80 passed). `git diff --check` passes.

## Implementation contract delivered

- `src/riff/migrations/014_pipeline_runs.sql` stores one logical `(run_date, policy_version)` run and durable per-stage state, attempts, counts, timing, errors, model usage, and cost estimates.
- `src/riff/operations.py` provides `DailyPipeline` and `PipelineRepository`. It replays only incomplete stages, enforces independent caps, marks `FAILED` versus `EMPTY`, and uses a row-locked identity claim for duplicate attempts.
- `src/riff/worker.py` and `riff worker --fixture ... [--resume]` invoke the same one-shot path; `GET /operations/{run_id}` exposes the structured report.
- The pipeline delegates evidence seeding and Riff publication to existing stage services; it does not reimplement their validation or call external providers in tests.

## Execution contract

Expected implementation surface: `src/riff/worker.py` and a new persisted
pipeline-run repository/orchestrator module; migration `014_pipeline_runs.sql`;
focused tests in `tests/test_operations.py` plus deterministic boundary
fixtures under `tests/fixtures/operations/`; and operator documentation in
`README.md` and `docs/architecture.md`. Equivalent module names are acceptable
only if these persistence, CLI, fixture, and documentation contracts remain.

Canonical persistence contract: one logical `(run_date, policy_version)` run
has stages `COLLECT`, `RECEIPT`, `CAPABILITY`, `PROFILE`, `SIGNAL`, `RIFF`, and
`PUBLISH`, each with `PENDING`, `RUNNING`, `COMPLETE`, or `FAILED` status,
attempt count, input/output counts, policy/version, timestamps, and error
details. A run is `SUCCEEDED`, `EMPTY`, or `FAILED`; only a durable `COMPLETE`
stage may advance its cursor. Duplicate identities are no-ops, not a second
publication.

Behavior matrix:

| Condition | Required result |
|---|---|
| Clean fixture | Each stage completes and publishes zero–three Riffs |
| Failure in any stage | Stage is `FAILED`; run report exposes the error; resume retries only incomplete work |
| Same date/policy rerun | Existing run/result returned with no duplicate records or completed provider calls |
| Concurrent same identity | One writer publishes; loser reports inspectable no-op/conflict |
| Input volume above configured bounds | Collection may continue, but expensive receipt/reasoning stages enforce independent caps |
| Policy version changes | New run identity/version; prior results remain queryable |
| Successful zero-Riff result | Run is `EMPTY`, distinct from `FAILED` |

Authority and side effects: the orchestrator may call only the existing stage
interfaces and local configured providers; it must not bypass repository
validation, invent evidence, or silently retry paid model calls. Tests use
offline fixtures and injected failures; no network, credentials, scheduler
daemon, or subprocess is required for verification. The one-shot CLI is the
same path used by the documented scheduler example.

Fixtures and criterion map: provide positive, zero-Riff, malformed-input,
partial-failure, repeated-run, concurrent-attempt, policy-change, and
unsupported-stage fixtures. `test_successful_funnel`,
`test_resume_after_each_stage_failure`, `test_concurrent_duplicate_run`,
`test_independent_caps`, `test_failed_vs_empty`, and `test_policy_version_fork`
must map directly to the acceptance criteria above and report stage/model-call
counts.

## Implementation latitude

Database-backed stage state and an operating-system scheduler are sufficient. Do not add a queue or workflow engine unless a demonstrated v0.1 failure cannot be solved simply.
