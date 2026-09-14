# G04 — Ingest incremental job-market evidence

**Status:** Queued  
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

- [ ] Initial, unchanged, and incremented fixture runs store only the expected new or changed job evidence.
- [ ] An exact repost is linked/collapsed without deleting its retrieval history; a materially changed description is versioned.
- [ ] Twenty distinct postings from one employer retain one correlated employer identity rather than twenty apparent organizations.
- [ ] Ambiguous employer aliases remain inspectable and reversible instead of being irreversibly merged.
- [ ] Compensation, seniority, or dates absent from a source remain null/unknown and are not synthesized.
- [ ] Stored postings can be searched by employer, role text, date, and source through the evidence store.
- [ ] A fixture/import workflow can populate representative data without credentials or network access.

## Verification evidence

Run the one-company-burst and repost/change fixtures and report logical posting, raw-version, retrieval, and employer counts. Demonstrate an expired posting remains retrievable.

## Implementation latitude

The PRD does not mandate a job provider. Prefer an official API, permitted feed, or user-provided export over brittle scraping. If no live source is safely available, a production-quality import adapter plus clear provider seam meets this goal; G15 must still disclose the dogfood data source.
