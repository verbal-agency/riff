# G40 — Compose approved live ingestion into the daily worker

**Status:** Complete
**Depends on:** G13, G21, G31, G34, G35, G38
**Unlocks:** G41, G42, trustworthy live daily runs
**Canonical scenario:** `SC-LIVE-DAILY-001`

## Outcome

Riff's scheduled worker composes the already-reviewed ingestion runners into
one bounded daily path. It collects only approved, enabled sources, processes
new evidence through the existing receipt/capability/profile/signal stages,
and produces a current zero-to-three daily result without treating fixtures as
live evidence.

The worker must have explicit modes: an offline fixture replay for tests and a
deliberate live mode for network collection. A bare invocation must never claim
success while doing no work.

## User-visible proof

An operator can run one documented command from a terminal or cron that shows
which approved sources were attempted, how many new observations and receipts
were produced, whether the day was empty or published, and where any source or
stage failed. Repeating the command is idempotent.

## Scope

- Add a composition layer over the existing RSS/technical-writing, engineer
  RSS, GitHub monitoring, permitted job, and enabled raw-signal runners.
- Preserve each runner's cursor, retry, provenance, retention, and origin
  contract; do not duplicate source-specific parsing or persistence.
- Feed newly committed evidence into the existing bounded receipt, capability,
  profile, signal, and daily-publication services.
- Make `--fixture` an explicit deterministic offline path and `--live` an
  explicit opt-in network path. A bare `riff worker` invocation fails with an
  actionable configuration/mode message.
- Exclude `FIXTURE`, `TEST`, `QUARANTINED`, and `UNCLASSIFIED` evidence from a
  live daily result by default. Preserve an explicit audit/include path for
  tests and diagnostics.
- Keep disabled, pending, terms-unreviewed, and unapproved sources out of
  network collection and report them as skipped with reasons.
- Use the same one-shot implementation for terminal and scheduler execution.

## Non-goals

- Broad crawling, automatic source approval, private GitHub access, arbitrary
  job-site scraping, or a queue/distributed worker system.
- Replacing existing collectors, source policies, provenance rules, or the
  conversational adapter.
- Selecting a production model provider; G42 owns that boundary.

## Acceptance criteria

- [x] `riff worker --fixture ...` replays the current durable fixture funnel;
  `riff worker --live` invokes only approved enabled collectors; bare `riff
  worker` exits nonzero and explains the required mode.
- [x] A recorded end-to-end run exercises at least one approved source runner,
  persists new evidence and receipts, and reaches a queryable daily result or
  an explicit successful empty result.
- [x] A live-mode run cannot select fixture/test/quarantined/unclassified rows
  as daily evidence, and its report labels every source and result as live,
  fixture, skipped, empty, or failed.
- [x] Cursor advancement occurs only after durable evidence/item outcomes; a
  rerun creates no duplicate evidence, receipts, or daily publication.
- [x] Disabled, pending, malformed, transiently failing, and permanently
  failing sources remain distinguishable and cannot silently become success.
- [x] Terminal and cron invocations call the same one-shot path and are covered
  by offline replay plus Postgres integration tests.
- [x] Operator documentation shows the exact fixture and live commands and
  states the network, credential, terms, and retention boundary.

## Deliverables

- A worker composition service and additive CLI mode/report changes.
- Source-to-stage outcome schema preserving source run IDs and origin policy.
- Fixture coverage for mixed source states, duplicate replay, disabled sources,
  and a successful live-shaped run using injected/recorded fetchers.
- Updated `README.md`, `docs/architecture.md`, and a numbered decision for the
  explicit live-mode boundary.

## Execution contract

Reuse `WritingIngestionRunner`, `GitHubIngestionRunner`, job collection,
GitHub monitoring, raw-signal ingestion, `EvidenceRepository`, receipt
processing, and the existing daily services. The worker is an orchestrator, not
a second parser. Tests must not require network access or credentials; live
behavior is exercised through injected clients and an explicitly authorized
operator smoke run.

## Verification evidence

- `.venv/bin/python -m pytest -q -m 'not postgres'` — 141 passed.
- Focused Postgres verification: `tests/test_live_worker.py` — 1 passed against
  Docker Postgres.
- Explicit fixture worker smoke for `2099-02-02` — seven stages complete,
  `SUCCEEDED`, three published fixture Riffs, one concise JSON report.
- `git diff --check` passes.

The complete Postgres suite was also run. It currently has an unrelated
connector promotion failure in
`tests/test_connector.py::test_http_connector_runs_read_promote_export_against_persisted_postgres`;
G40's focused Postgres path passes and no connector code changed in this goal.
