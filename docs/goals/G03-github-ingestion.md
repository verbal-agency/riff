# G03 — Ingest incremental GitHub evidence

**Status:** Complete
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

- [x] First, unchanged, and one-new-event collection runs have the expected nonduplicating counts.
- [x] A repository rename or organization transfer keeps one logical repository identity and valid old/new provenance.
- [x] Pagination resumes safely after a mid-run failure without missing or duplicating durable items.
- [x] Rate-limit exhaustion produces a resumable outcome and does not corrupt the cursor.
- [x] Fork, mirror, bot, repository, organization, and author identities needed for later independence estimates are retained.
- [x] Stored GitHub evidence is searchable by repository, organization, artifact type, and date through the evidence store.
- [x] Automated tests make no live GitHub requests; an optional smoke command can exercise live credentials separately.

## Verification evidence

Use recorded/synthetic multi-page data with a rate-limit interruption, repository rename, forked release, and new release. Report stored evidence and identity counts after retry.

## Implementation latitude

Choose the smallest GitHub surface that yields useful builder evidence for dogfooding. The adapter contract should allow later expansion without requiring every possible GitHub event in v0.1.

## Execution contract (satisfied in this cycle)

### Expected implementation surface

Extend `src/riff` with GitHub-specific configuration, an adapter implementing the G02 fetch/collection boundary, response normalization, and bounded artifact selection. Add migration `004_github_ingestion.sql` only if GitHub-specific persisted state is required; reuse G02 run/cursor/item tables otherwise. Add focused tests in `tests/test_github_ingestion.py`, recorded API fixtures under `tests/fixtures/github/`, and update `README.md` plus `docs/architecture.md` or a GitHub ingestion note. Equivalent paths are acceptable when the completion report names the substitutions and preserves this contract.

### Canonical domain and persistence contract

Use GitHub ingestion schema version `1` and reuse G01/G02 identity contracts:

| Concept | Required fields | Invariants |
|---|---|---|
| GitHub source configuration | `source_id`, `source_type=GITHUB`, configured repository/search scope, `enabled`, `config_version` | Scope is explicit and bounded; credentials are injected, never persisted. |
| Repository identity | provider repository ID, owner/organization, current name, canonical URL, fork/mirror flags | Provider ID is stable across rename/transfer; a rename does not create a new logical repository. |
| GitHub artifact | provider artifact ID/type, repository ID, author/contributor, observed/published timestamp, canonical URL, bounded content/snapshot | Artifact types are one of `REPOSITORY`, `RELEASE`, `README_CHANGE`, `ISSUE`, `DISCUSSION`, `DEPENDENCY`, `ACTIVITY`; unknown types are rejected. |
| Collection cursor/result | Reuses G02 cursor/run/item fields and outcomes | Pagination/rate-limit state is resumable; failed pages do not advance the cursor. |

Stars, forks, and popularity may be stored as metadata but are not an emerging-signal conclusion or an independence count by themselves. Forks, mirrors, bots, organizations, authors, and provider root IDs must remain queryable for later correlation.

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| First collection of a configured repository | Store bounded repository/artifact evidence through G01 and complete the cursor/run state. |
| Unchanged rerun | Produce no duplicate evidence versions and no cursor regression. |
| New release, README change, issue/discussion, or bounded activity event | Store one versioned artifact with provider ID, type, repository, author, and timestamp. |
| Repository rename or organization transfer | Retain one repository identity with updated display URL/name and historical provenance. |
| Fork, mirror, or bot-authored artifact | Store the flags/identity; do not count it as an unrelated independent root. |
| Mid-page process termination | Resume from the last durable page/item boundary without missing or duplicating artifacts. |
| HTTP 429/rate-limit response | Classify retryable, preserve the prior cursor, expose reset metadata, and make retry safe. |
| HTTP 401/403/404 or malformed response | Classify permanent/configuration failure without corrupting prior evidence/cursor. |
| Oversized diff/body | Apply the documented bound, retain the canonical URL/snapshot reference, and report truncation explicitly. |
| Stars-only/popularity-only change | Store weak metadata if useful; do not create a capability/trend artifact solely from it. |

### Authority and side-effect boundaries

This goal may perform read-only GitHub API requests for explicitly configured public scopes and mutate only local Riff Postgres/evidence state. It must not write to repositories, open issues, execute target code, invoke models, publish Riffs, alter capabilities/profile/decisions, or send private profile data. Tokens use the injected HTTP client and are redacted from logs/errors. Normal tests use recorded responses; a live credential smoke test is optional and must be separately invoked.

### Offline fixtures and state controls

Record multi-page repository/release data; README change; issue/discussion; contributor activity; rename/transfer; fork/mirror; bot; dependency material; new/unchanged rerun; mid-page termination; 429 with reset metadata; 401/403/404; malformed JSON; oversized content; unsupported artifact type; and popularity-only change. Verify pagination checkpoint/replay, duplicate calls, rate-limit retry, content truncation, credential redaction, and stop conditions. There is no model or expensive-reasoning budget in G03; API page/item limits and rate-limit backoff ceilings must be explicit.

### Criterion-to-test/artifact map

| G03 criterion | Required proof artifact |
|---|---|
| Incremental nonduplicating collection | `test_github_three_passes` with provider-ID/evidence counts |
| Rename/transfer identity | `test_repository_rename_preserves_identity` |
| Pagination/rate limit | `test_rate_limit_preserves_cursor_until_retry` |
| Fork/mirror/bot correlation metadata | `test_related_repository_flags_are_retained` |
| Bounded content | `test_oversized_artifact_is_truncated_and_referenced` |
| Searchable G01 evidence | `test_github_artifacts_are_traceable_and_searchable` |

## Cycle verification (2026-09-14)

- `.venv/bin/python -m pytest` → **22 passed, 21 skipped** without a configured database.
- Against an isolated temporary PostgreSQL instance, `.venv/bin/python -m riff migrate` applied `004_github_ingestion`; `.venv/bin/python -m pytest -m postgres` → **21 passed**.
- Fixture tests verified first/unchanged/new-event collection, rename and transfer alias history, page replay after rate limiting, mid-run replay, fork/mirror/bot identity, bounded content references, and searchable G01 traceability.
- `git diff --check` and `.venv/bin/python -m compileall -q src tests` passed.
