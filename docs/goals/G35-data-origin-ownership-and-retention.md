# G35 — Govern data origin, fixture ownership, and retention

**Status:** Complete
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
  `data_origin` (`LIVE`, `FIXTURE`, `TEST`, `QUARANTINED`, `UNCLASSIFIED`), an optional
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

- [x] A migration adds origin/owner/policy fields without breaking existing
  provenance joins; all new fixture writers populate them.
- [x] A dry-run identifies the known G26/G27 synthetic project projections and
  their dependent recommendations without selecting live source/evidence rows.
- [x] Applying cleanup removes only explicitly owned fixture/test projections,
  leaves live evidence and audit history intact, and is repeatable with zero
  additional deletions.
- [x] Default reports and project recommendations exclude fixture, test, and
  quarantined data; an explicit include mode exposes them for audits.
- [x] Malformed/nonstandard records retain raw payloads, receive a typed
  quarantine reason, and cannot raise provenance confidence or become live
  collection inputs.
- [x] Retention/archival policy is versioned, dry-runnable, and records what it
  would remove; no garbage collection occurs without explicit operator apply.
- [x] Offline and Postgres tests cover backfill, ownership scoping, foreign-key
  cleanup, idempotence, filtering, quarantine, retention preview, rollback,
  provenance preservation, and protection of operator-owned daily results.
- [x] Operator documentation gives one-line preview/apply/rollback/report
  commands and explains when an isolated test database remains preferable.

## Execution contract

### Expected implementation surface

- Add `src/riff/data_governance.py` with origin classification, ownership
  resolution, quarantine, cleanup preview/apply, retention preview/apply, and
  immutable audit reporting. Add migration
  `src/riff/migrations/023_data_governance.sql` (or the next available number)
  with additive nullable columns and audit tables.
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

### Authority and side-effect boundaries

- Reads and dry-runs may inspect Postgres and recorded fixtures only. No
  cleanup or retention command may call GitHub, mutate a source registry, or
  invoke a model.
- Apply requires an explicit `CLEANUP` or `RETENTION` confirmation plus an
  origin and owner/run selector. The transaction must lock and validate all
  dependent rows before deleting or archiving anything.
- Live evidence, daily Riffs, and operational failure history are protected by
  an explicit live-origin predicate and may not be selected by fixture/test
  cleanup.

### Deterministic behavior matrix and test map

| Input/state | Required result | Verification |
|---|---|---|
| Known `g26-*`/`g27-*` projection | `FIXTURE` with owner and evidence dependency count | `test_backfill_known_projects` |
| Ambiguous legacy row | `UNCLASSIFIED`, reported, never auto-cleaned | `test_ambiguous_rows_are_reported` |
| Dry-run with origin + owner | Stable deletion/archive plan and input fingerprint; no writes | `test_cleanup_preview_is_non_mutating` |
| Apply same plan twice | First applies; second reports zero additional changes | `test_cleanup_is_idempotent` |
| Dependency would orphan live evidence | Transaction aborts with typed dependency error | `test_cleanup_protects_live_evidence` |
| Malformed/nonstandard payload | Raw payload retained; `QUARANTINED` and typed reason | `test_quarantine_preserves_raw_payload` |
| Default report query | Excludes `FIXTURE`, `TEST`, `QUARANTINED`, and `UNCLASSIFIED` | `test_reports_are_live_only_by_default` |
| Explicit audit include | Returns bounded non-live rows with origin labels | `test_reports_include_audit_origins` |
| Retention preview/apply | Versioned plan and immutable audit; no apply without confirmation | `test_retention_preview_and_apply` |
| Rollback/restart after failure | Prior transaction remains intact; rerun is safe | `test_cleanup_failure_rolls_back` |

Use `tests/fixtures/data_quality/origins-v1.json` for positive, ambiguous,
malformed, contradictory, partial-failure, and ownership-collision cases.
Postgres tests must create a unique owner/run scope and clean only those rows;
they must not truncate the operator database.

## Handoff

The goal is complete when the known synthetic project rows can be previewed and
removed safely, default reports show live-only results, and future origin and
retention policies are executable without changing the provenance model.

## Verification

Migration `023_data_governance` applied successfully. Known daily and G26/G27
synthetic rows were backfilled with explicit `FIXTURE` ownership. The cleanup
dry-run selected eight owned G27 projections and eight snapshots with no
exploration dependencies; no live evidence or daily result was selected. The
focused Postgres test verified owner-scoped deletion, dependency ordering,
repeatability, and repository preservation. Full offline verification passed.
Applying the known cleanup remains confirmation-gated and has not been run.
