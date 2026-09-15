# G31 engineer-source provenance verification

## Result

The engineer-source collection path is implemented and verified through the
existing RSS/Postgres pipeline. Riff now has a dedicated
`data-quality engineer-sources` report that groups only by explicit
`engineer_source_id` metadata and separates fixture evidence from non-fixture
evidence. The initial G31 pass approved three reviewed feeds and completed live
smoke collection. The subsequent 2026-09-15 expansion pass approved 13
additional native feeds; the three URL-only candidates remain outside RSS.

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
- Existing RSS cursor/idempotence tests remain green; automated tests use no
  credentials or live HTTP. The explicitly authorized live smoke runs stored
  15 Simon Willison items, 212 Eugene Yan items, and 53 Lilian Weng items.

## Current operational database finding

The configured local database initially had reviewed, enabled projections for
three engineer sources. The current expanded registry has 16 reviewed,
enabled feed-backed projections; the expansion report records current
per-source coverage and separates test-created rows from live evidence.

The following counts are the initial G31 snapshot, before the expansion:

- Simon Willison: 47 non-synthetic items (69 total, including fixture rows).
- Eugene Yan: 212 non-synthetic items (216 total); one earlier 404 run remains
  recorded as a failed run.
- Lilian Weng: 53 non-synthetic items (57 total, including fixture rows).

The report still includes test-created rows from prior shared-database runs;
they are explicitly separated by `fixture` metadata and are not promoted into
confidence merely because they exist.

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

The checked-in selections record explicit `ENABLE` decisions, reviewer
`riff-operator`, and review date `2026-09-15`; the initial three use
`CONFIRMED` permission and the 13-source expansion uses `USER_PROVIDED`
permission. Project/apply and live collection remain bounded to the explicit
first-party endpoints and the `url_metadata_bounded_text` retention mode. No
credentials were used.
