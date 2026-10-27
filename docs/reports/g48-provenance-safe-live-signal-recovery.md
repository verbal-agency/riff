# G48 verification report — provenance-safe live signal recovery

Date: 2026-10-26

## Outcome

G48 is complete. Riff now treats live readiness as a provenance and ownership
property rather than trusting a `LIVE` label, and it can run a bounded replay
without absorbing unrelated same-day evidence. The replay path also uses a
run-date signal window, so replaying the same inputs does not drift with the
wall clock.

## Implementation verified

- `src/riff/data_governance.py` reports source owner, canonical root, fetch
  policy, latest collection health, and distinct `FAILED`, `PARTIAL`, `RUNNING`,
  `NEVER_COLLECTED`, `EMPTY`, `USABLE`, `DISABLED`, `REVIEW_REQUIRED`,
  `UNCONFIGURED`, and `FIXTURE_ONLY` states.
- `src/riff/live_worker.py` derives the ranking window from the requested run
  date. This fixes replay instability caused by using `datetime.now()` during
  ranking.
- Source- and collection-run-scoped replay, collection-run origin metadata,
  stable audit reason codes, and non-destructive test-source classification are
  covered by the existing G48 governance path and focused tests.

## Database recovery

The non-destructive repair command was run with explicit confirmation:

```text
uv run riff data-quality repair-origins --limit 5000 --confirm REPAIR_ORIGINS
```

Audit ID: `eda1a63f-c6a2-422f-bd3d-1d4ff3f2efbc`

The audit classified five fixture sources, 109 test sources, 278 test evidence
rows, and 458 test retrieval rows; 25 collection runs were repaired and 96
remained unresolved. No live evidence was quarantined by the repair. It changed
metadata and readiness only; it did not delete raw evidence.

## Clean source-scoped replay

```text
RIFF_REASONING_PROVIDER=deterministic uv run riff worker --replay-live \
  --replay-source-id writing-engineer-simon-willison \
  --since 2026-01-01T00:00:00+00:00 --limit 50 --date 2026-10-26 \
  --policy-version g48-clean-20261026 --resume
```

Run ID: `b1ba6f51-1179-5242-a8ff-9e9299867f94`

The run consumed three `LIVE` receipts from one approved source and returned
`EMPTY` / `INSUFFICIENT_EVIDENCE`. The publication gate correctly required two
independent provenance roots and reported that only one was present. This is a
valid result: it proves the trusted lane and scope boundary work without
manufacturing a recommendation from a single author.

## Verification commands

- Focused G48/live-worker tests: `13 passed`.
- Full suite: `282 passed, 2 warnings`.
- `git diff --check`: passed.

## Remaining limitation

The shared development Postgres database still contains some random UUID-named
rows created by older integration tests. Known fixture/test identities are now
classified and disabled safely, but rows without ownership metadata cannot be
reclassified by name without risking real evidence. `BL-G48-001` routes that
problem to isolated test databases or explicit test-owned origin metadata and a
preview-first cleanup. This is not a G48 blocker because those ambiguous rows
are excluded from the trusted live lane.
