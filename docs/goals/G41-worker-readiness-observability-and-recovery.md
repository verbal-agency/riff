# G41 — Make daily worker runs observable, ready-checkable, and recoverable

**Status:** In progress
**Depends on:** G40, G30, G35
**Unlocks:** Reliable unattended scheduling and operator iteration
**Canonical scenario:** `SC-WORKER-OPERATIONS-001`

## Outcome

An operator can tell whether a daily run actually collected usable evidence,
why a source was skipped or failed, and whether a prior run is safe to resume.
The worker exposes a stable report and exit status instead of a silent success,
and abandoned runs cannot remain indefinitely indistinguishable from active
work.

## Scope

- Print or return a compact JSON run report containing run ID, mode, date,
  policy versions, source outcomes, stage counts, origin counts, retries,
  durations, model usage when available, and final status.
- Define stable outcome classifications: `SUCCEEDED`, valid `EMPTY`, `PARTIAL`,
  `FAILED`, `STALE_RECOVERED`, `NOOP`, `READINESS_FAILURE`, and
  `FIXTURE_ONLY`. A live run must never report `FIXTURE_ONLY`.
- Define documented exit codes: `0` for `SUCCEEDED` or valid `EMPTY`; `10` for
  `PARTIAL`; `11` for `NOOP`; `12` for `READINESS_FAILURE`; `13`
  for configuration errors; and `14` for operational failure. The JSON report
  remains authoritative when an external scheduler needs more detail.
- Add a source-readiness check that distinguishes never collected, empty,
  failed, disabled, pending-review, stale, fixture-only, and usable sources.
- Add a heartbeat/lease or equivalent stale-run policy with a bounded recovery
  path. Preserve the audit trail when a stale run is reclaimed.
- Expose the same report through the existing API/ChatGPT read surfaces and
  document a one-line cron invocation that can be monitored externally.
- Keep source health and worker health separate: a partial source failure must
  be visible without falsely converting a valid partial day into an empty day.

## Non-goals

- Building a monitoring platform, queue, autoscaler, or distributed scheduler.
- Automatically enabling a source because readiness is low.
- Deleting failed runs, evidence, or audit history to make health look better.
- Force-reclaiming a non-stale worker, or retrying an active provider call
  outside its recorded run and stage boundary.

## Acceptance criteria

- [ ] Every worker invocation emits a stable machine-readable report and a
  meaningful exit code; no successful report has zero stages unless it is an
  explicitly classified no-op.
- [ ] A report includes its outcome classification, remediation, mode, policy
  versions, source outcomes, stage attempts/counts/durations, origin counts,
  and any available provider usage without exposing secrets, raw prompts, or
  unrestricted source bodies.
- [ ] Readiness reports identify at least one usable source, or fail clearly
  with source-specific remediation rather than publishing unsupported Riffs.
- [ ] A deliberately abandoned run becomes reclaimable after the configured
  lease interval; `--resume` cannot reclaim a non-stale run, and concurrent
  attempts remain safe and inspectable.
- [ ] Reports distinguish valid empty, partial, failed, stale-recovered, and
  fixture-only outcomes and include source/stage counts.
- [ ] API/ChatGPT read operations and terminal output agree on the same report.
- [ ] Offline and Postgres tests cover restart, lease expiry, concurrent runs,
  mixed source health, exit codes, and report redaction.

## Deliverables

- Worker report/exit-status contract and stale-run migration or additive state.
- Readiness and health commands plus API/adapter projections.
- Operator runbook and cron example with failure handling.
- Focused tests and a recorded failure/recovery report.

## Execution contract

### 1. Reuse the durable pipeline state

- Extend `pipeline_runs` and `PipelineRepository`; do not create a second run
  store. Add migration `026_worker_operations.sql` with additive lease fields
  (`lease_owner`, `lease_expires_at`, `heartbeat_at`, and `recovery_count`) and
  an append-only `pipeline_run_events` audit table.
- A claim is transactional. A new run obtains a unique lease owner; a terminal
  run returns `NOOP` with reason `TERMINAL_RUN` without rewriting history; and
  a non-expired `RUNNING` lease returns `NOOP` with reason `ACTIVE_LEASE` and
  cannot be reclaimed.
- `--resume` may reclaim only an expired lease. It records a
  `STALE_RECLAIMED` event linked to the prior owner and resumes only incomplete
  stages. A completed stage is never re-run merely because the process restarted.
- The lease duration is configured through a bounded worker setting, defaulting
  to 15 minutes. Heartbeats occur at stage boundaries and around each source
  collection attempt so a long collection does not appear abandoned.

### 2. Canonical report and readiness projection

- Keep `PipelineRepository.report()` as the canonical report builder and have
  fixture, live, and live-replay paths add their mode-specific fields through a
  shared projection. Do not maintain separate terminal and ChatGPT report
  formats.
- Preserve current per-stage counts and source outcomes, then add stable
  classification, remediation, retry/lease state, origin counts, and provider
  usage fields when present. Partial source failures remain visible even when a
  run produces a valid empty result.
- Add `riff worker readiness` plus a read-only adapter/MCP operation. It reports
  each configured source as `USABLE`, `NEVER_COLLECTED`, `EMPTY`, `FAILED`,
  `DISABLED`, `PENDING_REVIEW`, `STALE`, or `FIXTURE_ONLY`, with a bounded
  remediation. It never enables or fetches a source.

### 3. Terminal and scheduler behavior

- Keep `riff worker --fixture`, `--live`, and `--replay-live` as explicit modes.
  The CLI prints the canonical JSON report and exits with the documented code;
  exceptions before a report become `CONFIGURATION_ERROR` or `FAILED` with a
  compact JSON error payload where practical.
- Document one monitored cron command and a corresponding readiness check. A
  scheduler can alert on nonzero codes while inspecting the report to distinguish
  partial collection, active-worker no-op, readiness failure, and failure.

### 4. Verification sequence

1. Add deterministic unit tests for classification, exit-code mapping, and
   redaction.
2. Add Postgres tests for active-lease rejection, stale reclaim, restart without
   duplicate completed stages, and append-only recovery history.
3. Add source-readiness fixtures for every readiness state and a mixed
   healthy/failed live-collection case.
4. Verify terminal, adapter, and MCP surfaces produce the same redacted report.
5. Record an operator scenario: begin a run, simulate abandonment, inspect
   readiness, resume it, and confirm the final report says `STALE_RECOVERED`.

G42 must consume this report and lease contract rather than creating parallel
provider health or retry state.
