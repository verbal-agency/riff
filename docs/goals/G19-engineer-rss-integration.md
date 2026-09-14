# G19 — Integrate approved engineer-authored RSS sources

**Status:** Complete
**Depends on:** G16, G17
**Unlocks:** Engineer-attributed technical-writing collection and richer source selection
**PRD references:** Sections 7–8, 22, 24.3, 26–29, 33

## Outcome

Riff can take an explicitly reviewed subset of the G17 engineer-source roster,
register its permitted RSS/Atom feeds in the existing technical-writing
pipeline, and retain engineer authorship, ownership, and correlation metadata
without silently enabling unreviewed collection.

## Project outcomes and scenarios advanced

- `SC-RSS-001` — Extend the reviewed, fixture-replayable RSS/Atom source set
  without treating feed volume or syndication as independent evidence.
- `SC-ENGINEER-SOURCE-001` — Carry a named engineer's authorship, employer, and
  correlation provenance from source selection into collected evidence.

## User-visible proof

An operator can inspect a selection manifest, see why each engineer feed is
eligible or blocked, preview the registry changes, and run the selected feeds
through the same fixture-backed RSS collector used by existing technical
sources. Each resulting Evidence Receipt remains attributable to the person,
source owner, organization-at-publication, and correlation group.

## Inputs

- `config/engineer_sources.json` and the approved G17 roster.
- `config/technical_sources.json` and `config/ingestion_sources.json`.
- The G02 RSS/Atom ingestion contract and G16 parser/feed-quality fixtures.
- G17's attribution, independence, permission, and retention rules.

## Scope

- Define a versioned engineer-RSS selection manifest that references existing
  `engineer_source_id` values rather than duplicating person records.
- Add an explicit per-source collection decision and review record. A source
  may be promoted only with a confirmed endpoint and terms/retention decision;
  roster approval alone must never enable collection.
- Project approved selections into the technical-writing registry while
  preserving source identity, canonical root, owner, person identity,
  organization-at-publication, artifact class, retention, cadence, and
  correlation group.
- Extend the RSS ingestion path to carry source-level engineer attribution in
  retrieval metadata and to apply the G17 rules for personal, employer,
  co-authored, syndicated, missing, and contradictory attribution.
- Provide a dry-run/validation path and an explicit enablement path that
  rejects pending, unavailable, or `NONE_FOUND` sources before any fetch.
- Replay selected feeds through deterministic fixtures, including incremental
  cursors, duplicate content, missing canonical links, stale/missing authors,
  employer authorship, and attribution drift.

## Non-goals

- Discovering additional engineers or GitHub sources (G17/G18).
- Scraping personal sites, using unofficial feed mirrors, bypassing paywalls,
  or fetching any source during tests.
- Automatically enabling every native RSS candidate or treating a personal
  source as independent from its employer or cited upstream source.
- Replacing the existing RSS collector, evidence store, receipt processor, or
  independence/ranking policy.

## Acceptance criteria

- [x] A schema-versioned selection manifest references at least three G17
  engineer sources and records `engineer_source_id`, collection decision,
  permission/terms review, reviewer/date, retention mode, and fixture plan.
- [x] A valid, confirmed selection can be previewed and projected into both
  source registries without losing canonical URL, source root, owner,
  attribution, or correlation metadata; projection is idempotent.
- [x] Pending, unavailable, `NONE_FOUND`, malformed, duplicate, or
  credential-bearing selections are rejected before registry mutation or a
  network request, with a source-specific error.
- [x] Selected feeds use the existing incremental RSS/Atom runner and preserve
  `engineer_source_id`, person identity, source ownership, organization, and
  correlation group in every stored evidence record's retrieval metadata.
- [x] Personal, employer-authored, co-authored, syndicated, missing-author,
  and attribution-drift fixture cases produce the documented provenance and
  quarantine/skip outcomes; no case is guessed into independent evidence.
- [x] A selected source remains disabled unless its selection explicitly has a
  collection-enable decision; the CLI reports enabled, pending, blocked, and
  dry-run outcomes distinctly.
- [x] Offline replay demonstrates first-run storage, unchanged rerun
  idempotence, cursor advancement after durable writes, and retry behavior for
  transient versus permanent feed failures.
- [x] Documentation gives the operator a review checklist, promotion command,
  rollback/disable procedure, and a statement that no live collection occurs
  without per-source approval.

## Deliverables

- `config/engineer_rss_selections.json` with a secret-free schema-versioned
  selection contract; all fixture selections remain disabled by default.
- A validator/projection module under `src/riff` (for example,
  `engineer_rss.py`) and CLI commands for dry-run, validate, and explicit
  promotion/enablement.
- Any additive source-registry or retrieval-metadata changes needed to retain
  engineer attribution; no new evidence table is required unless the existing
  JSON metadata contract cannot satisfy the criteria.
- Focused fixtures under `tests/fixtures/engineer_sources/` and
  `tests/test_engineer_rss_integration.py` covering the acceptance matrix.
- Updated `docs/engineer-sources.md`, `docs/ingestion-sources.md`, and
  `README.md` with the operator workflow and safety boundary.

## Execution contract

### Expected implementation surface

Extend the source CLI and registry validation seam, add the selection manifest
and projection service, and reuse `WritingIngestionRunner`, `parse_feed`,
`EvidenceSubmission`, and existing cursor/run persistence. The focused test
file is `tests/test_engineer_rss_integration.py`; fixtures belong under
`tests/fixtures/engineer_sources/`. A migration is not expected because
`EvidenceSubmission.retrieval_metadata` is already persisted as JSONB; add one
only if an equivalent backward-compatible metadata path is proven insufficient.

### Canonical selection and persistence contract

Selection manifest schema is `1`. Each entry must contain
`selection_id`, `engineer_source_id`, `registry_source_id`, `endpoint`,
`source_root`, `source_ownership`, `person_id`, `organization_at_publication`,
`correlation_group`, `permission_status`, `retention_mode`, `reviewed_at`,
`reviewed_by`, `collection_decision`, `fixture_plan`, and `enabled`.

`collection_decision` is one of `DRY_RUN`, `PENDING`, `ENABLE`, or `BLOCK`.
`enabled` may be `true` only when `collection_decision=ENABLE`,
`permission_status` is `CONFIRMED` or `USER_PROVIDED`, and `reviewed_at` and
`reviewed_by` are non-empty. The projection must preserve the stable
`registry_source_id`; it must not create a second source for the same canonical
endpoint and root.

For every stored engineer-attributed item, retrieval metadata contains:
`adapter`, `engineer_source_id`, `person_id`, `person_name`,
`source_ownership`, `organization_at_publication`, `source_root`,
`correlation_group`, and an attribution disposition. Employer and syndicated
items retain their organization/root correlation even when the named engineer
is an author.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Confirmed `ENABLE` selection with valid native RSS | Dry-run shows one projection; explicit apply enables only that source |
| `PENDING`, `UNAVAILABLE`, or `NONE_FOUND` selection | Validation fails before mutation/fetch; source remains disabled |
| Missing reviewer/date, malformed URL, duplicate ID, or credential-like value | Field-specific validation error; no registry or DB mutation |
| Duplicate endpoint/root already registered | Reuse stable source identity; projection is idempotent and reports unchanged |
| Personal item with matching source-owned attribution | Store engineer metadata with `PERSONAL` disposition |
| Employer item authored by engineer | Store author plus employer correlation; never mark as independent personal evidence |
| Co-authored or syndicated item | Preserve all available authors/root relation; do not duplicate independent observations |
| Missing or contradictory author/canonical link | Quarantine or permanent item failure per G17 policy; never infer identity |
| Unchanged second fixture replay | Zero new evidence and no cursor regression |
| Transient fetch failure | Record retryable failure; leave cursor unchanged |
| Permanent malformed item | Record permanent/quarantined failure; advance only past that item |

### Authority and side-effect boundaries

Manifest validation, dry-run, and all tests are local and offline. Projection
may mutate only the repository's versioned manifests and local Postgres source
configuration. Explicit enablement is an operator action and must not be
inferred from G17 roster approval. Live HTTP fetching is allowed only through
the existing bounded RSS fetcher after enablement; tests use recorded fixtures,
no credentials, and no external network. No source content is published,
shared, or sent to a model as part of this goal.

### Fixtures and criterion-to-test map

Provide positive confirmed personal-feed, employer-author-filter, and
co-authored cases; negative pending/none-found/credential/malformed cases;
duplicate and syndicated cases; attribution drift and missing-link cases; and
first-run/unchanged-rerun/transient-failure fixtures.

| Criterion | Proof |
|---|---|
| Selection schema and review gate | `test_selection_manifest_requires_review_and_decision` |
| Idempotent registry projection | `test_projection_is_idempotent_and_preserves_identity` |
| Unsafe selections blocked before side effects | `test_pending_and_unsafe_selections_fail_closed` |
| Attribution metadata in RSS evidence | `test_engineer_metadata_survives_rss_ingestion` |
| Independence/correlation dispositions | `test_personal_employer_and_syndicated_provenance` |
| Cursor, duplicate, and failure behavior | `test_replay_cursor_and_failure_matrix` |
| CLI/operator workflow | `test_cli_dry_run_and_explicit_enablement` |

## Verification

- Validate the selection and both projected source manifests offline.
- Run the focused integration tests and the full offline suite.
- Run the PostgreSQL ingestion tests against an isolated temporary database.
- Confirm a fixture replay performs no live HTTP request and no source is
  enabled unless the fixture contains an explicit confirmed decision.
- Run `git diff --check` and verify no credentials or private URLs are present.

## Handoff

Only selections with explicit per-source terms/retention approval may be
enabled. Sources that remain pending or lack a permitted machine-readable
endpoint stay in the engineer roster and do not enter collection. Any
author-specific non-RSS adapters remain a separate follow-up rather than being
silently substituted here.

## Cycle verification (2026-09-14)

- `.venv/bin/python -m riff source engineer-rss validate --manifest config/engineer_rss_selections.json` — 3 selections valid.
- `.venv/bin/python -m riff source engineer-rss preview --manifest config/engineer_rss_selections.json` — all 3 reported `pending`; none enabled or fetched.
- `.venv/bin/python -m pytest -q tests/test_engineer_rss_integration.py tests/test_writing_ingestion.py tests/test_rss_source_expansion.py tests/test_engineer_sources.py` — 19 passed, 2 skipped (PostgreSQL marker).
- `RIFF_DATABASE_URL=... .venv/bin/python -m pytest -m postgres tests/test_engineer_rss_integration.py tests/test_writing_ingestion_fixtures.py tests/test_ingestion_sources.py tests/test_migrations.py` — 10 passed.
- `.venv/bin/python -m pytest -q -m 'not postgres'` — full offline suite passed.
- `uv lock --check`, JSON validation, and `git diff --check` passed.
- The temporary PostgreSQL run used an isolated database; no live feed request or credential was used.
