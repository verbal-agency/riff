# G35 — Govern data origin, fixture ownership, and retention

**Status:** Queued
**Depends on:** G22, G27, G30, G31
**Unlocks:** Trusted live-data evaluation, safe fixture cleanup, and future quarantine/garbage-collection policy
**PRD references:** Sections 7–9, 22, 29, 33
**Canonical scenario:** `SC-DATA-GOVERNANCE-001`

## Outcome

Riff distinguishes live, fixture, test, and quarantined data at the persistence
boundary. The current shared development database can be cleaned without
guessing from row IDs, while future retention, archival, normalization, and
garbage-collection policies can evolve without destroying provenance.

## User-visible proof

An operator can preview owned fixture rows, understand their dependencies,
clean them transactionally, and rerun coverage or recommendation reports with
live data only. Malformed or nonstandard inputs remain inspectable as
quarantined records instead of being silently discarded.

## Scope

### 1. Origin and lifecycle contract

- Add additive origin metadata to fixture-capable persisted records:
  `data_origin` (`LIVE`, `FIXTURE`, `TEST`, `QUARANTINED`), an optional
  `origin_run_id`/owner, and `policy_version`.
- Require new fixture/test writers to set origin metadata explicitly; retain
  stable raw payloads and evidence hashes.
- Ensure integration-test fixtures cannot truncate or overwrite the shared
  operator dogfood database; tests must use an isolated database or
  origin/owner-scoped cleanup.
- Backfill only confidently identified existing fixtures (including known
  `g26-*`/`g27-*` project rows); leave ambiguous rows `UNCLASSIFIED` and report
  them for review.

### 2. Safe cleanup and retention

- Add a bounded terminal command with dry-run as the default, explicit apply
  confirmation, transactional dependency ordering, and an audit summary.
- Delete only rows owned by the requested fixture/test origin. Never delete
  live raw evidence merely because it is empty, failed, old, duplicated by
  version history, or not cited by a current Riff.
- Add configurable retention/archival classes for collection runs, source
  projections, recommendations, and quarantined payloads. Garbage collection
  must be reviewable and idempotent.

### 3. Query and normalization policy

- Make coverage, project matching, and recommendation reports exclude
  `FIXTURE`, `TEST`, and `QUARANTINED` records by default, with an explicit
  bounded include option for tests and audits.
- Preserve raw nonstandard input and store a canonical normalized projection;
  validation failures carry a typed reason and do not fabricate evidence.
- Record the policy/version and origin in quality reports so changes remain
  comparable over time.

## Non-goals

- Broad deletion or truncation of the development database, `docker compose
  down -v`, or removal of live provenance to make counts look cleaner.
- Inferring origin from arbitrary text, silently promoting fixtures to live
  evidence, or replacing source-specific parsers with one universal parser.
- Removing legitimate changed-content evidence versions or operational failure
  history without an explicit retention decision.

## Acceptance criteria

- [ ] A migration adds origin/owner/policy fields without breaking existing
  provenance joins; all new fixture writers populate them.
- [ ] A dry-run identifies the known G26/G27 synthetic project projections and
  their dependent recommendations without selecting live source/evidence rows.
- [ ] Applying cleanup removes only explicitly owned fixture/test projections,
  leaves live evidence and audit history intact, and is repeatable with zero
  additional deletions.
- [ ] Default reports and project recommendations exclude fixture, test, and
  quarantined data; an explicit include mode exposes them for audits.
- [ ] Malformed/nonstandard records retain raw payloads, receive a typed
  quarantine reason, and cannot raise provenance confidence or become live
  collection inputs.
- [ ] Retention/archival policy is versioned, dry-runnable, and records what it
  would remove; no garbage collection occurs without explicit operator apply.
- [ ] Offline and Postgres tests cover backfill, ownership scoping, foreign-key
  cleanup, idempotence, filtering, quarantine, retention preview, rollback,
  provenance preservation, and protection of operator-owned daily results.
- [ ] Operator documentation gives one-line preview/apply/rollback/report
  commands and explains when an isolated test database remains preferable.

## Execution contract

### Expected implementation surface

- Add a migration and origin/retention repository under `src/riff/`.
- Extend `riff data-quality` with bounded `origins`, `cleanup`, and `retention`
  subcommands; keep destructive operations confirmation-gated.
- Update ingestion, project-map, recommendation, and quality-report query
  paths to use the origin policy. Add fixtures under
  `tests/fixtures/data_quality/` and focused tests in
  `tests/test_data_governance.py`.
- Update `README.md`, `docs/architecture.md`, and add a numbered decision for
  origin classification and retention semantics.

### Canonical contracts and illegal states

- `data_origin` is one of `LIVE`, `FIXTURE`, `TEST`, `QUARANTINED`, or
  `UNCLASSIFIED`; `UNCLASSIFIED` is never eligible for automatic promotion.
- Cleanup requires an origin selector and owner/run scope; no unscoped delete
  is a valid command. A failed dependency check aborts the transaction.
- Quarantine preserves raw content and provenance but is excluded from daily
  signals and confidence calculations until explicitly reviewed.
- Retention actions produce an immutable audit record and include policy and
  input fingerprints.

## Handoff

The goal is complete when the known synthetic project rows can be previewed and
removed safely, default reports show live-only results, and future origin and
retention policies are executable without changing the provenance model.
