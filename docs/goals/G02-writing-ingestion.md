# G02 — Add incremental ingestion and curated technical writing

**Status:** Queued  
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
