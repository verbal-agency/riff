# G31 — Execute and verify engineer-source provenance collection

**Status:** Blocked
**Depends on:** G17, G19, G22, G30
**Unlocks:** Real engineer-attributed evidence for provenance calibration and source-quality review
**PRD references:** Sections 7–8, 22, 24.3, 26–29, 33
**Canonical scenarios:** `SC-ENGINEER-SOURCE-001`, `SC-EPISTEMIC-001`, `SC-DATA-QUALITY-001`

## Outcome

Riff turns a reviewed subset of the engineer-source roster into evidence that
can actually be inspected in Postgres. Each enabled source has an explicitly
reviewed endpoint, permission/terms decision, retention mode, reviewer, and
fixture or live-run record. Stored receipts preserve person, ownership,
organization-at-publication, source root, attribution disposition, and
correlation group without guessing missing authorship.

This goal closes the operational gap identified by G30: the roster currently
contains engineer and organization metadata, but none of those configured
sources has produced a receipt in the database.

## Scope

1. Select at least three native RSS/Atom entries from the G17 roster and record
   per-source endpoint, terms/retention review, reviewer/date, and an explicit
   `ENABLE`, `PENDING`, or `BLOCK` decision in the existing G19 manifest.
2. Run the selected entries through the existing technical-writing collector
   using recorded fixtures first, then perform an explicitly authorized live
   smoke run for sources whose endpoint and terms review are confirmed.
3. Verify persisted retrieval metadata and Evidence Receipts for person,
   ownership, organization, source root, correlation group, and attribution
   disposition. Preserve `fixture=true` when evidence is synthetic.
4. Reconcile source coverage and provenance-quality reports so enabled,
   pending, blocked, empty, and failed engineer sources are distinguishable.
5. Record source-level outcomes and route unavailable or non-RSS entries to a
   future adapter goal rather than substituting unofficial mirrors or inferred
   identity.

## Non-goals

- Discovering additional engineers or inventing authorship from article text.
- Enabling the entire roster, scraping sites without a permitted feed, bypassing
  paywalls/robots, or using unofficial RSS mirrors.
- Changing independence weights, capability semantics, or the G30 repair logic.
- Sending raw source content or a full engineer profile to a model.

## Acceptance criteria

- [ ] At least three G17 native-RSS selections have a recorded endpoint,
  permission/terms decision, retention mode, reviewer/date, and fixture plan;
  only explicitly confirmed `ENABLE` selections are eligible for collection.
- [x] Registry projection and `source sync` are idempotent and enable only the
  confirmed selections; pending, blocked, unavailable, or `NONE_FOUND` entries
  remain disabled with a source-specific reason.
- [x] Fixture replay stores at least one item per selected source through the
  existing RSS runner and Postgres, with all required engineer provenance keys
  present in retrieval metadata and searchable evidence.
- [ ] An explicitly authorized live smoke run, or an operator-provided
  first-party response captured under the reviewed retention policy, produces at
  least one non-synthetic receipt for an enabled engineer source; the report
  records the source, run ID, item outcome, and whether evidence is fixture or
  live.
- [x] Personal, employer-authored, co-authored, syndicated, missing-author, and
  attribution-drift cases preserve the G17 disposition rules; no identity or
  independence claim is inferred.
- [x] First run, unchanged rerun, transient failure, permanent parse failure,
  and cursor/checkpoint replay are idempotent and leave no skipped evidence.
- [ ] A data-quality/source-coverage report shows the before/after engineer
  receipt count and explains any remaining zero-evidence source; provenance
  confidence does not increase from synthetic evidence alone.
- [x] Operator documentation gives the one-line validate, preview, project,
  sync, collect, disable, rollback, and report commands, plus the explicit
  live-network and credential boundary.

## Deliverables

- Updated `config/engineer_rss_selections.json` with review records and no
  credentials; unapproved entries remain disabled.
- Additive collector/report changes only where the focused integration exposes
  a missing metadata or coverage field; no replacement collector.
- Recorded fixtures under `tests/fixtures/engineer_sources/` and focused tests
  in `tests/test_engineer_rss_integration.py` plus the Postgres data-quality
  assertion.
- `docs/reports/g31-engineer-source-provenance.md` and updates to
  `docs/engineer-sources.md`, `docs/ingestion-sources.md`, and `README.md`.

## Execution contract

### Expected implementation surface

Reuse `src/riff/engineer_rss.py`, `src/riff/engineer_sources.py`,
`WritingIngestionRunner`, `EvidenceRepository`, and the existing `riff source`
and `riff ingest` commands. The focused test surface is
`tests/test_engineer_rss_integration.py`; Postgres assertions use an isolated
database and the existing migration fixture. A migration is not expected.

### Canonical persistence contract

Selection schema remains version `1`. For every stored item, retrieval metadata
must contain `engineer_source_id`, `person_id`, `person_name`,
`source_ownership`, `organization_at_publication`, `source_root`,
`correlation_group`, `attribution_disposition`, and the existing `fixture`
indicator when applicable. Source identity remains the stable
`registry_source_id`; prior receipts and versions are immutable.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Confirmed `ENABLE` + valid feed/fixture | Source projects, collects, and records provenance |
| `PENDING`, `BLOCK`, `NONE_FOUND`, or missing review | Validation refuses before fetch or mutation |
| Missing/contradictory author | Quarantine or typed permanent outcome; never infer |
| Employer/co-authored/syndicated item | Preserve organization/root/correlation and documented disposition |
| Unchanged replay | Zero new evidence; cursor and receipt counts unchanged |
| Transient failure | Retryable item/run outcome; cursor unchanged until durable commit |
| Permanent parse failure | Permanent/quarantined outcome; no fabricated receipt |
| Disable after collection | Future run skips source; prior evidence remains searchable |

### Authority and side-effect boundaries

Manifest review and live enablement are operator actions. Tests and fixture
replays use no network or credentials. Live collection may contact only the
explicitly reviewed first-party endpoint through the bounded RSS fetcher; it
must not scrape arbitrary URLs or publish content. Raw content remains in the
existing evidence store and is not sent to a model by this goal.

### Criterion-to-proof map

| Criterion | Proof |
|---|---|
| Selection and enablement gate | `test_selection_manifest_requires_review_and_decision`, `test_cli_dry_run_and_explicit_enablement` |
| Metadata propagation | `test_engineer_metadata_survives_rss_ingestion`, Postgres receipt/retrieval assertions |
| Attribution and independence | `test_personal_employer_and_syndicated_provenance` |
| Replay and failure safety | `test_replay_cursor_and_failure_matrix` |
| Coverage/RCA closure | `test_engineer_source_coverage_before_and_after_collection`, `riff data-quality report` artifact |
| Operator boundary | `docs/reports/g31-engineer-source-provenance.md`, no-live-network fixture run, `git diff --check` |

## Handoff

The goal is complete only when at least one explicitly approved source has
produced non-synthetic evidence or the operator has recorded a first-party
response under the reviewed retention policy. Sources without a permitted
machine-readable endpoint remain disabled and are routed to a separately
approved adapter goal.

## Cycle verification (2026-09-15)

- Offline selection/projection checks: **5 passed**.
- Focused Postgres engineer-source checks: **4 passed**, including three-source
  fixture collection, attribution-drift refusal, metadata persistence, and
  source-sync idempotence.
- Clean temporary Postgres replay: **5 passed** across engineer-source and
  data-quality tests; the temporary database was removed after verification.
- Full offline suite: **111 passed, 91 skipped**.
- Added `riff data-quality engineer-sources --limit 100`, which reports explicit
  engineer IDs and separates fixture from non-fixture evidence.
- The checked-in selection manifest remains `PENDING`/disabled for all three
  sources. No live source was enabled or fetched; the non-synthetic evidence
  acceptance criterion therefore remains pending operator approval.
- The shared development database contains test-created engineer rows; this is
  recorded as `BL-G31-001` and must not be treated as live provenance.

## Blocker

Completion requires an operator decision for at least three native-RSS
selections: confirmed endpoint, terms/retention policy, reviewer, and review
date. Until that decision is recorded, the manifest must remain
`PENDING`/disabled and Riff must not perform a live collection. Fixture replay
and all Riff-side verification are complete; no further safe implementation can
produce the required non-synthetic receipt without that external authority.
