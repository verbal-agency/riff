# G09b — Identify and qualify concrete ingestion sources

**Status:** Ready  
**Depends on:** G09a  
**Unlocks:** G13, G15  
**PRD references:** Sections 7–8, 22, 24.3, 26–29, 33

## Outcome

Riff has a reviewed, concrete source plan for its first dogfood corpus: named
technical-writing feeds, GitHub scopes, and a permitted job-market input, each
with an access, retention, provenance, and fixture strategy.

## User-visible proof

An operator can inspect one source manifest and understand exactly what Riff will
collect, why it is relevant, what evidence it can retain, how often it may be
queried, and what happens when access or retention is unavailable.

## Scope

- Identify at least two named technical-writing sources, two bounded GitHub
  repository/search scopes, and one permitted job-market API/feed/export path.
- Prefer source-owned RSS/Atom, official APIs, or user-provided exports; do not
  assume scraping permission or store credentials in the manifest.
- Record canonical endpoint/scope, source type, rationale, expected artifact
  types, terms/permission status, rate or request limits, retention mode,
  identity/provenance fields, cadence, and a fixture/replay plan.
- Define inclusion/exclusion rules so popularity-only or duplicate syndication
  cannot masquerade as independent evidence.
- Identify a fallback or explicit “not available” state for every category;
  missing access must remain visible rather than silently substituting a source.

## Non-goals

- Implementing new adapters, crawling, live collection, source-quality scoring,
  or changing G02–G04 behavior.
- Selecting sources solely because they are popular or easy to scrape.

## Acceptance criteria

- [ ] A schema-versioned manifest names at least five concrete initial scopes:
  two technical-writing sources, two GitHub scopes, and one permitted job input.
- [ ] Every entry has a canonical endpoint/scope, source type, collection method,
  permission/terms note, cadence, retention mode, expected artifacts, and
  provenance/identity fields.
- [ ] The manifest contains no passwords, tokens, private URLs, or implied
  credentials; unavailable permissions are explicitly marked.
- [ ] A reviewer can map each source to a fixture/replay plan and a bounded
  request policy, including rate-limit and failure handling.
- [ ] The source set includes an explicit duplicate/syndication policy and does
  not count popularity as independent evidence.
- [ ] The plan records a dated review/owner and a decision for each fallback;
  unresolved source access is a named blocker, not an implicit assumption.

## Deliverables

- `config/ingestion_sources.json` schema version `1` with the reviewed source
  entries and no secrets.
- `docs/decisions/0009-ingestion-source-selection.md` with rationale, terms,
  retention, fallback, and review date.
- `docs/ingestion-sources.md` operator notes and fixture/replay checklist.
- Focused manifest validation tests in `tests/test_ingestion_sources.py`.

## Execution contract

### Expected implementation surface

Add a manifest validator under `src/riff` or reuse the existing source-registry
validation seam; add the manifest, ADR, operator note, and focused tests. Do not
modify adapter code unless required to represent a manifest field, and record
any such substitution in the completion report.

### Canonical domain and behavior matrix

Manifest schema version is `1`. Each entry must include `source_id`, `name`,
`source_type` (`TECHNICAL_WRITING`, `GITHUB`, or `JOBS`), `endpoint_or_scope`,
`access_method`, `permission_status`, `retention_mode`, `cadence`,
`expected_artifacts`, `identity_fields`, `fixture_plan`, `rate_limit_policy`,
and `fallback`. `permission_status` is one of `CONFIRMED`, `USER_PROVIDED`,
`PENDING_REVIEW`, or `UNAVAILABLE`.

| Condition | Required result |
|---|---|
| Complete valid entry | Manifest validator accepts it. |
| Missing permission/retention/fixture detail | Validation fails with field-level errors. |
| Embedded secret or private credential | Validation fails and identifies the entry. |
| Unavailable source | Entry remains explicit with `UNAVAILABLE` and fallback. |
| Duplicate/syndicated scope | Entry records exclusion/correlation handling. |

### Authority and side-effect boundaries

This goal may inspect public source documentation and repository configuration,
but it must not authenticate, scrape, write to upstream systems, or collect
live evidence. It mutates only the local manifest, ADR, notes, and tests.

### Criterion-to-test map

| Criterion | Proof |
|---|---|
| Concrete category coverage | `test_manifest_has_required_source_categories` |
| Required metadata | `test_manifest_entries_are_operationally_complete` |
| No secrets | `test_manifest_rejects_credentials` |
| Fixture and bounded policy | `test_manifest_fixture_and_rate_policy` |
| Explicit fallback/duplicate policy | `test_manifest_records_fallbacks_and_correlation_policy` |

