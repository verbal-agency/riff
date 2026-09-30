# G41 — Make daily worker runs observable, ready-checkable, and recoverable

**Status:** Queued
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
- Define exit codes for succeeded, valid empty, failed, already-running/no-op,
  configuration error, and readiness failure.
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

## Acceptance criteria

- [ ] Every worker invocation emits a stable machine-readable report and a
  meaningful exit code; no successful report has zero stages unless it is an
  explicitly classified no-op.
- [ ] Readiness reports identify at least one usable source, or fail clearly
  with source-specific remediation rather than publishing unsupported Riffs.
- [ ] A deliberately abandoned run becomes reclaimable after the configured
  lease interval; concurrent attempts remain safe and inspectable.
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
