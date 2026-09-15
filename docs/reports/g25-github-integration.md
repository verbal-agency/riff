# G25 GitHub discovery integration — 2026-09-15

## Outcome

An approved discovery candidate now enters the existing G03 GitHub collector
without bypassing review or enabling live collection. The promoted fixture
scope remains disabled in the registry; the integration test performs an
explicit fixture-only opt-in against Postgres.

## Verification

The test discovers `acme/riff-runtime` from the recorded seeded-input fixture,
requires `APPROVE` followed by `PROMOTE`, and asserts the exact registry
projection in `tests/fixtures/github/discovery/promoted-scope-v1.json`.
The projected source preserves its discovery run, seed/query attribution,
provider repository ID, correlation metadata, and disabled state.

The test then configures that source in Postgres with an explicit fixture-only
enablement and runs `GitHubIngestionRunner` (the G03 path) using the recorded
repository, release, issue, and README responses:

```text
test_promoted_fixture_scope_reuses_g03_pipeline  -> 1 passed
tests/test_github_ingestion.py (Postgres)         -> 8 passed
tests/test_github_discovery.py                    -> 9 passed
```

The first collection stored six searchable evidence items. A repeat stored
zero new items and recorded six duplicates. Repository identity, artifact
metadata, and source-scope provenance remained queryable; discovery metadata
was also carried into each retrieval record so downstream receipt and signal
processing can trace the evidence back to the reviewed candidate.

No live GitHub request, repository write, credential persistence, or checked-in
source enablement occurred. The integration source ID is uniquely isolated per
test run to avoid contamination from shared development database rows.

## Acceptance status

All G25 acceptance criteria are verified. G25 is complete and unblocks G26's
user-owned project inventory and snapshot work.
