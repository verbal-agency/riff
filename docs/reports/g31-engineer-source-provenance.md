# G31 engineer-source provenance verification

## Result

The engineer-source collection path is implemented and verified through the
existing RSS/Postgres pipeline. Riff now has a dedicated
`data-quality engineer-sources` report that groups only by explicit
`engineer_source_id` metadata and separates fixture evidence from non-fixture
evidence.

## Automated evidence

- Offline engineer selection and projection tests: **5 passed**.
- Focused Postgres engineer-source tests: **4 passed**.
- Clean temporary Postgres replay of the engineer-source and data-quality
  markers: **5 passed**; the temporary database was removed after verification.
- The three-source integration uses recorded first-party-shaped fixtures for
  Simon Willison, Eugene Yan, and Lilian Weng; each stores evidence and retains
  person, ownership, organization, source root, correlation group, and
  attribution disposition metadata.
- Attribution drift is recorded as a permanent failure and does not create an
  evidence row.
- Existing RSS cursor/idempotence tests remain green; no live HTTP request or
  credential is used by the automated suite.

## Current operational database finding

The configured local database still has no clean, reviewed engineer-source
projection. The current engineer coverage report shows test-created rows for
`engineer-simon-willison`, including duplicate random source IDs and a mixture
of fixture and unmarked synthetic evidence. These rows came from integration
tests that use the shared development database; they are not evidence that a
reviewed live source has been collected. No user data was deleted to hide this
condition.

This is a test-isolation/RCA finding, not a reason to infer authorship or to
promote the current rows into provenance confidence. Future Postgres tests
should use an isolated database or clean test-owned rows before evaluating live
source diversity.

The test-isolation follow-up is recorded as `BL-G31-001` in
`docs/backlog.md`.

## Operator workflow

```sh
uv run riff source engineer-rss validate --manifest config/engineer_rss_selections.json
uv run riff source engineer-rss preview --manifest config/engineer_rss_selections.json
uv run riff data-quality engineer-sources --limit 100
uv run riff source engineer-rss review --selection-id <selection-id> --reviewed-at <YYYY-MM-DD> --reviewed-by <operator> --permission-status CONFIRMED --decision ENABLE --confirm ENABLE --apply
uv run riff source engineer-rss project --selection-id <selection-id> --apply
uv run riff source sync --registry config/technical_sources.json
uv run riff ingest --source-type TECHNICAL_WRITING --source-id <registry-source-id>
uv run riff source disable --source-id <registry-source-id>
```

The checked-in selections remain `PENDING` and disabled. Project/apply and live
collection require the operator to record per-source endpoint, terms,
retention, reviewer, and date. A live run is not claimed by this report; it is
the explicit final acceptance gate for G31.
