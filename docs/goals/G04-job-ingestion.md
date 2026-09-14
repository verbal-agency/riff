# G04 — Ingest incremental job-market evidence

**Status:** Complete
**Depends on:** G02  
**Unlocks:** G05  
**PRD references:** Sections 7.1, 8, 22, 24.3

## Outcome

Riff can incrementally ingest applied-AI job postings from at least one legally and operationally suitable configured source, normalize the essential posting metadata, and preserve employer identity so repeated hiring from one company can later be correlated.

## User-visible proof

An operator can run a bounded job collection, see canonical postings with company, role, dates, content, and available compensation, and rerun without treating reposts or repeated company listings as new independent evidence.

## Inputs

- G02's source-adapter, cursor, run-state, and retry contracts.
- A permitted job feed/API/export and representative fixture corpus.

## Scope

- Implement the G02 adapter contract for at least one documented job source or user-supplied feed/export.
- Include a fixture/import path so development and evaluation never depend on a fragile live job site.
- Preserve canonical posting URL/provider ID, company, role, seniority when inferable, compensation as stated, responsibilities/content, location where relevant, publication/observation dates, and source provenance.
- Represent employer identity separately from display name and retain unresolved identity uncertainty.
- Detect exact/canonical reposts while preserving changed versions and repeated distinct roles.
- Bound collection by explicit configured queries relevant to the primary user.

## Non-goals

- Applying to jobs, résumé matching, scraping sources contrary to their terms, inferring missing compensation, or concluding that one company's burst is a market trend.
- Capability/technology extraction; G05 owns that transformation.

## Required properties

- Source access method and operational constraints are documented.
- Removal or expiration upstream does not delete historical evidence.
- Missing metadata remains unknown rather than guessed.
- Same-company postings retain a shared employer identity where confidently known, with reversible aliases.
- Tests are fixture-driven and make no live job-site requests.

## Deliverables

- At least one usable job adapter/importer and query configuration.
- Employer identity/alias representation sufficient for later correlation.
- Fixtures for reposts, changed descriptions, one-company bursts, ambiguous company names, missing compensation, and expired listings.
- Collection and source-compliance documentation.

## Acceptance criteria

- [x] Initial, unchanged, and incremented fixture runs store only the expected new or changed job evidence.
- [x] An exact repost is linked/collapsed without deleting its retrieval history; a materially changed description is versioned.
- [x] Twenty distinct postings from one employer retain one correlated employer identity rather than twenty apparent organizations.
- [x] Ambiguous employer aliases remain inspectable and reversible instead of being irreversibly merged.
- [x] Compensation, seniority, or dates absent from a source remain null/unknown and are not synthesized.
- [x] Stored postings can be searched by employer, role text, date, and source through the evidence store.
- [x] A fixture/import workflow can populate representative data without credentials or network access.

## Verification evidence

Run the one-company-burst and repost/change fixtures and report logical posting, raw-version, retrieval, and employer counts. Demonstrate an expired posting remains retrievable.

## Implementation latitude

The PRD does not mandate a job provider. Prefer an official API, permitted feed, or user-provided export over brittle scraping. If no live source is safely available, a production-quality import adapter plus clear provider seam meets this goal; G15 must still disclose the dogfood data source.

## Execution contract (satisfied in this cycle)

### Expected implementation surface

Extend `src/riff` with a bounded job-source/import adapter, posting normalization,
employer identity persistence, and a one-shot runner on the G02 ingestion
contracts. Add migration `005_job_ingestion.sql` only when employer-specific
state cannot fit the existing tables. Add focused tests in
`tests/test_job_ingestion.py` and recorded/import fixtures under
`tests/fixtures/jobs/`. Update `README.md` and `docs/architecture.md` (or a
focused job-ingestion note) with source-compliance and operator instructions.
Equivalent paths are acceptable when the completion report names them.

### Canonical domain and persistence contract

Use job-ingestion schema version `1` and preserve G01/G02 identities:

| Concept | Required fields | Invariants |
|---|---|---|
| Job source configuration | `source_id`, `source_type=JOBS`, permitted endpoint/import format, `enabled`, `config_version` | Access method is explicit; credentials are injected and never persisted. |
| Employer identity | stable employer ID when supplied, display name, normalized name, aliases, confidence/state | Ambiguous aliases remain reversible and are not silently merged. |
| Job posting | provider posting ID or canonical URL, employer ID/alias, title, seniority (nullable), compensation (nullable), location (nullable), published/observed dates, bounded content | Missing fields remain null; no inferred compensation or seniority is stored as fact. |
| Collection cursor/result | Reuses G02 cursor/run/item fields and outcomes | Reposts deduplicate by source identity; changed descriptions create G01 versions; failures do not advance past unprocessed data. |

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| First fixture import | Store every valid posting and employer identity; complete run/cursor state. |
| Unchanged rerun | Create no duplicate evidence versions; preserve retrieval history and report duplicate/replay outcomes. |
| New posting | Store one new posting with canonical URL/provider ID and advance the cursor after evidence commit. |
| Exact repost | Reuse one logical posting identity, retain each retrieval, and do not delete historical evidence. |
| Materially changed description | Create a new G01 evidence version linked with `VERSION_OF`. |
| Twenty postings from one employer | Correlate to one confident employer identity rather than twenty organizations. |
| Ambiguous employer alias | Retain an inspectable alias candidate/state; do not merge it irreversibly. |
| Missing compensation, seniority, or date | Persist null/unknown and never synthesize a value. |
| Expired/deleted upstream posting | Keep prior evidence retrievable; do not erase it. |
| Unauthorized/unsupported source or malformed import | Classify permanent failure, preserve prior cursor, and expose an actionable error. |

### Authority and side-effect boundaries

This goal may read only from explicitly configured, permitted job feeds/APIs or
local user-provided exports and may mutate only Riff's local Postgres
evidence/collection state. It must not apply to jobs, scrape against provider
terms, execute target code, invoke models, publish recommendations, or send
profile data. Credentials are injected at request time and redacted from logs.
Normal tests are offline and fixture-driven; any live smoke operation is
separate and opt-in.

### Offline fixtures and state controls

Provide fixtures for an initial corpus, unchanged replay, one new posting, exact
repost, changed description, a twenty-posting one-company burst, ambiguous
employer aliases, missing compensation/seniority/date, expired listing,
malformed record, unsupported source, and transient import/read failure. Verify
cursor checkpoint/replay, duplicate retrievals, version linking, employer alias
reversibility, explicit bounds, and stop behavior. No model or paid-provider
budget is allowed in G04; import/page/item limits must be explicit.

### Criterion-to-test/artifact map

| G04 criterion | Required proof artifact |
|---|---|
| Incremental runs | `test_job_three_passes` with posting/evidence counts |
| Repost/change behavior | `test_repost_retrieval_and_changed_version` |
| Employer correlation | `test_one_employer_burst_correlates_identity` |
| Alias uncertainty | `test_ambiguous_employer_alias_is_reversible` |
| Missing metadata | `test_missing_fields_remain_unknown` |
| Searchability | `test_jobs_are_searchable_by_employer_role_date` |
| Offline operation | `test_import_fixture_requires_no_network_or_credentials` |

## Cycle verification (2026-09-14)

- `.venv/bin/python -m pytest` → **23 passed, 28 skipped** without a configured database.
- Against an isolated temporary PostgreSQL instance, `.venv/bin/python -m riff migrate` applied `005_job_ingestion`; `.venv/bin/python -m pytest -m postgres` → **28 passed**.
- Fixture tests verified incremental import, exact repost retrieval history, changed-description versioning, twenty-posting employer correlation, reversible ambiguous aliases, null missing metadata, expired evidence retention, malformed-row isolation, and employer/role/date search.
- The documented `riff source add --source-type JOBS` plus `riff job import --file ...` operator path returned a successful three-posting run without credentials or network access.
- `git diff --check` and `.venv/bin/python -m compileall -q src tests` passed.
