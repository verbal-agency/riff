# G30 data-quality remediation and RCA

Date: 2026-09-15

## Remediation run

Migration `017_data_quality_maintenance` was applied to the Docker Postgres
database. The repair command was then run twice:

```text
riff data-quality repair --stale-after-seconds 3600
```

First run:

- Receipt metadata rows changed: 0 (the migration had already backfilled the
  missing IDs and source type).
- Stale collection runs reconciled: 26 — 13 with recorded item outcomes became
  `SUCCEEDED` with `STALE_RUN_RECONCILED`; 13 with no item outcomes became
  `FAILED` with `STALE_RUN_NO_ITEM_RESULTS`.
- Riffs recalibrated: 3.

Second run:

- Metadata updates: 0.
- Stale runs: 0.
- Riff recalibrations: 0 (`skipped_current: 3`).

This demonstrates idempotence and preserves the original Riff scores and
decision tables.

## Post-remediation checks

| Check | Result |
| --- | --- |
| Receipt source/evidence IDs present | 199/199 |
| Receipt source type present | 199/199 |
| Receipt retrieval linkage | 199/199 |
| Evidence payload/hash invariants | 0 violations |
| Riffs with current calibration fields | 3/3 |
| Riffs with explicit interpretation | 3/3 |
| Fixture ceiling violations | 0 |
| Collection runs still `RUNNING` | 0 |
| Source coverage | 807 collected, 26 empty, 13 failed, 13 never collected |

## Root-cause analysis of prior findings

1. **Missing receipt IDs/source type — fixed.** Older receipt producers stored
   only partial extractor metadata. The canonical evidence/source join was
   always sufficient to recover these fields, so migration 017 and the
   repeatable backfill now fill only absent keys.
2. **Missing author/organization — not a corruption defect.** The 26 reviewed
   engineer-source configurations contain person and organization metadata,
   but none of those configured sources has produced a receipt in this
   database. No author or employer is inferred. This remains an evidence
   collection gap, routed to the engineer-RSS operational follow-up.
3. **Stale `RUNNING` runs — fixed.** Runs were created before an interrupted
   process exited and had no terminal reconciliation. The new age-bounded
   command derives a terminal state only from recorded item outcomes and stores
   a completion reason.
4. **Enabled sources with no evidence — exposed, not silently repaired.** The
   source coverage report distinguishes `NEVER_COLLECTED`, `EMPTY`, and
   `FAILED`. The remaining 39 enabled sources without usable evidence are a
   collection/readiness issue, not something safe to fabricate.
5. **Orphan receipts — expected.** 196 receipts are not cited by the three
   currently persisted daily Riffs; they belong to the wider evidence corpus,
   not dangling foreign keys. Receipt-to-retrieval linkage is complete.
6. **Repeated job URLs — expected version history.** 508 posting rows cover 28
   URLs; 27 URLs have multiple evidence versions (maximum 78). This is the
   intended changed-content/retrieval history, not duplicate rows with the same
   evidence identity.
7. **Sparse current Riffs — expected development state.** All three current
   Riffs are fixture-only and therefore calibrated to 0.05 epistemic
   confidence. This is correctly disclosed, but real-source dogfooding is still
   required before judging recommendation quality.
8. **Coverage-report performance/scope — fixed in implementation.** The first
   report query joined source, evidence, and run rows before applying its sample
   limit, which made it unnecessarily expensive and caused its state counts to
   describe only the sample. Pre-aggregated evidence/run CTEs now compute totals
   across all 860 sources and apply the limit only to returned detail rows.

## Residual risk and routing

- The absence of author/organization evidence should be addressed by running
  the already-reviewed engineer RSS sources and verifying receipt propagation;
  it is recorded as `BL-G30-001` in the backlog rather than inferred here.
- Failed, empty, and never-collected enabled sources need operator review before
  they are treated as a healthy production feed set.
- No raw evidence was included in this report or emitted by the checks.
