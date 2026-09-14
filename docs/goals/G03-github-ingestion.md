# G03 — Ingest incremental GitHub evidence

**Status:** Queued  
**Depends on:** G02  
**Unlocks:** G05  
**PRD references:** Sections 7.2, 8, 22, 24.3

## Outcome

Riff can incrementally collect builder activity from a configured set of GitHub repositories and searches while preserving repository, organization, contributor, and root-source identity for later independence reasoning.

## User-visible proof

An operator can collect a configured repository, rerun without duplication, then observe a new release or meaningful repository-document change appear as new versioned evidence with GitHub provenance.

## Inputs

- G02's source-adapter, cursor, run-state, and retry contracts.
- Configured GitHub repositories/searches and recorded or synthetic API fixtures.

## Scope

- Implement the G02 adapter contract for GitHub using an authenticated API when configured and a documented constrained fallback if useful.
- Collect repository metadata plus selected evidence such as releases/release notes, README or key-document changes, issues/discussions, contributor activity, and dependency or implementation-pattern material that is available through bounded queries.
- Preserve GitHub organization, repository, author/contributor, source-native IDs, timestamps, URLs, and event/artifact type.
- Add per-repository or query cursors and handle pagination and rate limits.
- Make the configured repositories/searches explicit and reviewable.
- Preserve stars and popularity metadata as weak context only; do not turn it into a signal in this goal.

## Non-goals

- Mirroring entire repositories, compiling or executing target code, broad GitHub crawling, capability extraction, or trend conclusions.
- Treating forks, mirrors, bots, or repeated release syndication as independent confirmation.

## Required properties

- Collection is read-only against target repositories.
- Renames/transfers retain repository identity when the provider exposes it.
- Deleted/inaccessible upstream items do not erase previously stored evidence.
- Large bodies and diffs are bounded by an explicit policy and retain a reference to the original.
- Bot and fork/mirror metadata is preserved so later stages can correlate it.

## Deliverables

- GitHub adapter and configuration model.
- Incremental pagination/cursor behavior and rate-limit handling.
- Recorded or synthetic fixtures for releases, README change, issue/discussion, rename/transfer, fork/mirror, and rate-limit response.
- Collection documentation including credential scopes.

## Acceptance criteria

- [ ] First, unchanged, and one-new-event collection runs have the expected nonduplicating counts.
- [ ] A repository rename or organization transfer keeps one logical repository identity and valid old/new provenance.
- [ ] Pagination resumes safely after a mid-run failure without missing or duplicating durable items.
- [ ] Rate-limit exhaustion produces a resumable outcome and does not corrupt the cursor.
- [ ] Fork, mirror, bot, repository, organization, and author identities needed for later independence estimates are retained.
- [ ] Stored GitHub evidence is searchable by repository, organization, artifact type, and date through the evidence store.
- [ ] Automated tests make no live GitHub requests; an optional smoke command can exercise live credentials separately.

## Verification evidence

Use recorded/synthetic multi-page data with a rate-limit interruption, repository rename, forked release, and new release. Report stored evidence and identity counts after retry.

## Implementation latitude

Choose the smallest GitHub surface that yields useful builder evidence for dogfooding. The adapter contract should allow later expansion without requiring every possible GitHub event in v0.1.
