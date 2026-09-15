# G30 — Repair persisted data quality and close the feedback loop

**Status:** Complete
**Depends on:** G22, G29
**Unlocks:** Trustworthy recurring collection and real-evidence Riff evaluation
**PRD references:** Sections 3–6, 9, 13–15, 18, 21, 27–29, 32–33
**Canonical scenarios:** `SC-EVIDENCE-001`, `SC-RIFF-001`, `SC-DB-001`

## Objective

Repair the high-value data-quality issues found in the Docker Postgres spot
check, then rerun the checks and write root-cause analysis for every remaining
anomaly. The maintenance path must be idempotent, auditable, and safe to run
from a terminal or cron without touching raw evidence content.

## In scope

1. Backfill receipt provenance metadata from canonical source, source-item,
   evidence, and reviewed ingestion-source metadata while preserving existing
   values and fixture labels.
2. Reconcile stale `RUNNING` collection runs using an explicit age bound and a
   deterministic terminal status/reason derived from recorded item outcomes.
3. Provide a read-only source-coverage report showing configured, enabled,
   collected, empty, failed, and fixture-backed sources.
4. Recompute persisted Riff provenance summaries when the policy version or
   summary shape is stale, preserving the generated score and decision history.
5. Rerun the complete spot-check suite and document RCA, residual risk, and
   whether each anomaly is fixed, expected version history, or a future goal.

## Explicit exclusions

- Do not delete evidence, receipts, source rows, job versions, or decisions.
- Do not infer authors, organizations, production status, or source identity
  when the canonical metadata is absent.
- Do not silently mark a live collection successful; stale runs with no
  completed item evidence must remain failed/partial with an audit reason.
- Do not add live network collection or model calls.

## Execution contract

- Expected implementation: migration `017_*`, maintenance functions in
  `src/riff/ingestion_repository.py` and `src/riff/provenance.py`, CLI
  `riff data-quality report|reconcile|recalibrate`, focused tests in
  `tests/test_data_quality.py`, and RCA report under `docs/reports/`.
- Canonical run states remain `RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`;
  reconciliation may transition only stale `RUNNING` rows to terminal states.
- Backfill is additive JSONB merge with canonical IDs taking precedence only
  when the receipt field is absent; fixture/synthetic markers are never
  removed.
- Recalibration is deterministic and keyed by `provenance-policy-v1`; it must
  be safe to repeat and must not create decisions or status transitions.
- All mutation commands require the configured Postgres URL and print bounded
  JSON summaries; report commands are read-only.

## Acceptance criteria

- [x] A repeatable migration/command repairs missing receipt IDs, source type,
  root, author, and organization metadata only when canonical reviewed data is
  available, with before/after counts.
- [x] No collection run older than the configured stale threshold remains
  `RUNNING` after reconciliation; each changed row has a terminal status and
  auditable reason, and repeated reconciliation is a no-op.
- [x] Source coverage reports identify enabled sources with zero evidence and
  distinguish never-collected, failed, and fixture-only sources.
- [x] Existing Riffs have current provenance summaries including the explicit
  interpretation, while candidate/generated scores and decision history are
  unchanged; repeating recalibration is idempotent.
- [x] The post-remediation spot check confirms payload/hash/retrieval/linkage
  invariants and explains every residual anomaly, including job version history
  and orphan receipts.
- [x] Offline tests cover additive backfill, stale-run status derivation,
  coverage classification, recalibration idempotence, fixture preservation,
  privacy, and illegal-state protection; Postgres tests exercise the real
  migration and commands.

## Handoff

Report commands, row counts before/after, RCA for all findings, migration and
backward-compatibility notes, and the remaining evidence gap before real-source
dogfooding.
