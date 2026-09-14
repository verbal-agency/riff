# G02 — Add incremental ingestion and curated technical writing

**Status:** Ready
**Depends on:** G01  
**Unlocks:** G03, G04, G05  
**PRD references:** Sections 7.3–8, 26–29

## Outcome

Riff has a reusable incremental-collection framework proven by ingesting a manually curated set of technical-writing feeds. Repeated runs fetch only new or changed material and persist durable cursors and run outcomes.

## User-visible proof

An operator can configure a small source list, run collection twice, and see that the second run stores no duplicate material. Adding a new feed item stores only that item and records its provenance.

## Inputs

- G01 evidence/provenance persistence and stable evidence identities.
- A small user-curated feed list plus deterministic RSS/Atom and discovery fixtures.

## Project outcomes and scenarios advanced

- **Outcomes:** incremental collection; curated technical-writing evidence; resumable source cursors.
- **Scenarios:** `SC-EVIDENCE-001` and the ingestion portion of `SC-DOGFOOD-001`.

## Scope

- Define the source-adapter contract, collection cursor/checkpoint, collection run, item result, retry classification, and partial-failure semantics.
- Add a versioned, manually editable curated-source registry.
- Support common technical-writing feeds or an equivalently open, stable primary mechanism.
- Retrieve and store original article content or a faithful snapshot when permitted; preserve metadata when full content is unavailable.
- Treat Hacker News only as optional discovery input and resolve links to original artifacts rather than using popularity as primary evidence.
- Expose one-shot collection by source and source type.
- Record per-source collection counts, cursor movement, failures, and durations without leaking content.

## Non-goals

- Broad web crawling, automated source discovery, source-quality learning, or article summarization.
- GitHub and job-market adapters.
- Claiming that a feed item is important merely because it was collected.

## Required properties

- A source's cursor advances only to a point consistent with durably stored results.
- One source failure does not roll back successfully persisted items from unrelated sources.
- Retrying a partially failed run is safe and does not create duplicates.
- Rate limits, timeouts, malformed content, and unavailable full text have explicit outcomes.
- Network clients are injectable and fixture-backed in tests.

## Deliverables

- Generic collection contracts and persisted run/cursor state.
- Curated technical-writing source configuration.
- At least one real feed-compatible adapter plus fixture/replay tests.
- Optional HN discovery handling that records both discovery and root provenance if included.
- Operator commands and run summary.

## Acceptance criteria

- [ ] A fixture feed's first run stores all eligible items, its second unchanged run stores zero, and a later run stores only a newly added or changed item.
- [ ] Cursor state survives process termination and resumes without skipping an uncommitted item.
- [ ] A malformed item is quarantined or recorded as failed while other valid items complete.
- [ ] A transient request failure is distinguishable from a permanent parse/configuration failure and can be retried safely.
- [ ] Curated sources can be enabled, disabled, and labeled without a code change.
- [ ] If discovery input is implemented, the original linked artifact—not the discussion score—is stored as the root evidence, with the discovery relationship retained.
- [ ] An integration test proves raw evidence from this adapter is searchable and traceable through G01.

## Verification evidence

Run deterministic three-pass fixture collection (initial, unchanged, one-new-item) and record item counts, cursor values, and evidence IDs. Also exercise one partial-failure fixture.

## Implementation latitude

RSS/Atom is the preferred first mechanism because it is simple and source-owned. A small number of source-specific fetch rules is acceptable; a general-purpose crawler is not.

## Execution contract for the next Luna run

### Expected implementation surface

Extend `src/riff` with a source-registry/configuration module, generic ingestion contracts, cursor/run persistence, and one RSS/Atom-compatible technical-writing adapter. Add migration `003_ingestion_runs.sql` (or an equivalent next numbered migration), focused tests in `tests/test_writing_ingestion.py`, and adapter integration tests in `tests/test_writing_ingestion_fixtures.py`. Update `README.md` with configured source/run commands and add operational detail to `docs/architecture.md` or a focused ingestion note. Equivalent paths are acceptable only when the completion report names them and preserves this contract.

### Canonical domain and persistence contract

Use ingestion schema version `1`. The persistence layer must expose these concepts:

| Concept | Required fields | Invariants |
|---|---|---|
| Source configuration | `source_id`, `source_type`, `name`, `endpoint`, `enabled`, `config_version` | Reuses G01 source identity; disabled sources are not fetched; configuration has no embedded secret. |
| Collection cursor | `source_id`, `cursor_kind`, `cursor_value` (nullable), `updated_at` | One current cursor per source/cursor kind; it advances only after the corresponding evidence write is durable. |
| Collection run | `run_id`, `started_at`, `finished_at` (nullable), `status`, `source_ids`, `policy_version` | Status is one of `RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`; a run cannot finish twice. |
| Item result | `run_id`, `source_id`, `source_native_id`/`canonical_url`, `outcome`, `evidence_id` (nullable), `error_code` (nullable) | Outcome is one of `STORED`, `DUPLICATE`, `SKIPPED`, `FAILED_TRANSIENT`, `FAILED_PERMANENT`; failed items have no evidence ID. |

The adapter must return normalized metadata sufficient for G01 ingestion. Unknown source types, malformed feed entries, and invalid cursor values are typed validation failures. Secrets/tokens are obtained through an injected credential boundary and are never persisted in source configuration or run logs.

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| First run over an eligible fixture feed | Store every valid new item through G01; persist a completed run and cursor. |
| Unchanged feed rerun | Produce zero new evidence versions, `DUPLICATE`/`SKIPPED` item results, and no cursor regression. |
| One newly published item after the cursor | Store only that item and advance the cursor after its evidence transaction commits. |
| Changed content at an existing item | Reuse G01 versioning; record the new evidence ID, not a duplicate source item. |
| Malformed item among valid items | Record a permanent item failure/quarantine; persist valid siblings and a `PARTIAL` run. |
| Transient request failure | Preserve the prior cursor, classify `FAILED_TRANSIENT`, and make a retry safe. |
| Permanent auth/configuration/parse failure | Classify `FAILED_PERMANENT`, do not advance the cursor past unprocessed items, and expose an actionable run error. |
| Disabled or unsupported source | Do not fetch; return `SKIPPED`/typed unsupported result with no evidence mutation. |
| Process termination after some items | Resume from the last durable cursor/item boundary without duplication or skipping. |
| Optional HN discovery link | Persist the original linked artifact through G01 and retain the discovery relationship; discussion score is metadata only. |

### Authority and side-effect boundaries

This goal may perform network reads against explicitly configured technical-writing sources and mutate only Riff's local Postgres collection/evidence state. It must not write to remote sources, invoke models, execute target code, publish Riffs, alter capability/profile/decision state, or send private profile data. Credentials are injected only into adapter requests and redacted from exceptions/logs. Tests use recorded HTTP/fixture responses; live network access is an opt-in smoke operation, never part of normal verification.

### Offline fixtures and state controls

Record fixtures for a valid multi-page feed, empty/unchanged feed, one-new-item cursor advance, changed item, malformed XML/entry, missing date/title/link, transient timeout/429, permanent 401/parse failure, disabled source, unsupported source type, duplicate/replay, and process termination after a committed subset. Include a discovery link fixture if HN support is implemented. There is no model or expensive-reasoning budget in G02; request/item limits and retry ceilings must be explicit instead. Verify cursor checkpoint, replay, duplicate-call, retry, and stop behavior.

### Criterion-to-test/artifact map

| G02 criterion | Required proof artifact |
|---|---|
| First/unchanged/incremental runs | `test_fixture_feed_three_passes` with evidence/cursor counts |
| Cursor durability and safe retry | `test_cursor_advances_only_after_evidence_commit` and injected termination fixture |
| Malformed item isolation | `test_malformed_item_yields_partial_run` |
| Transient/permanent distinction | `test_retryable_timeout` and `test_permanent_parse_failure` |
| Configurable curated sources | `test_source_registry_enable_disable` |
| Discovery root provenance | `test_discovery_fixture_links_original_source` when enabled |
| G01 integration/search | `test_writing_evidence_is_traceable_and_searchable` |
