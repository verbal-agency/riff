# G17 — Identify and qualify engineer-authored sources

**Status:** Complete
**Depends on:** G16
**Unlocks:** Engineer-level source enrichment and a future source-selection goal
**PRD references:** Sections 7–8, 22, 26–29, 33

## Outcome

Riff has a separate, identity-aware map of useful sources written or maintained
by specific engineers and researchers, without conflating personal expertise,
employer announcements, conference appearances, and reposted material.

## User-visible proof

The operator can review a named engineer, the source they control or author, the
native feed/API status, the topics it covers, and the evidence limits before
adding that source to Riff.

## Inputs

- The G15 themes: durable execution, agent observability, workflow
  reconciliation, agent frameworks, evaluation, and reliable systems.
- The G16 source registry and its provenance/correlation rules.
- A user-reviewed roster of engineers, or a proposed roster for user approval.

## Scope

- Propose and qualify at least twelve named engineers/researchers across the
  current themes, including practitioners from workflow/runtime, agent
  frameworks, observability/evals, and distributed-systems or AI-safety work.
- For each person, locate source-owned blogs, newsletters, papers, talks,
  changelogs, podcasts, or GitHub activity; prefer native RSS/Atom or official
  APIs and record when none exists.
- Distinguish personal authorship from employer-owned publication, guest posts,
  interviews, conference programs, and community reposts.
- Record canonical URLs, author identity, organization at publication time,
  source ownership, feed/API status, cadence, terms/retention, expected
  artifacts, fixture plan, and fallback.
- Define how the same engineer's personal and employer sources correlate and how
  co-authored or syndicated work is counted.

## Non-goals

- Following private social accounts, scraping gated pages, using unofficial
  RSS mirrors as evidence, or inferring expertise from follower counts.
- Automatically treating an engineer's source as independent from their
  employer, collaborators, or cited upstream source.
- Implementing a new collector before the roster and permissions are reviewed.

## Acceptance criteria

- [x] A dated roster contains at least twelve named engineers/researchers and a
  rationale tied to an applied-AI capability theme.
- [x] Every person has at least one source decision: native feed/API accepted,
  public source pending review, or no permitted machine-readable source found.
- [x] Each source records author, owner, organization, root-source identity,
  canonical URL, terms/retention, cadence, artifact types, and fallback.
- [x] The report separates personal writing from employer, conference,
  co-authored, syndicated, and reposted evidence.
- [x] At least three sources are evaluated for identity ambiguity, stale feeds,
  missing canonical links, or attribution drift using recorded fixtures.
- [x] The user reviews the proposed roster before any source is enabled for
  collection. User approved the roster on 2026-09-14; every entry remains
  disabled pending individual terms review.

## Deliverables

- `docs/engineer-sources.md` with the named roster and source decisions.
- A versioned engineer-source manifest or additive section of the source
  manifest, with no credentials or private URLs.
- Attribution/correlation fixtures and focused validation tests.
- A follow-up list of sources requiring a future adapter rather than RSS.

## Verification

- Validate the manifest and attribution fixtures offline.
- Demonstrate that personal, employer, co-authored, and syndicated items retain
  distinct provenance and correlation metadata.
- Report unresolved permissions or attribution ambiguities as named blockers.

## Handoff

The approved roster becomes input to source selection; it does not itself
authorize live collection or change the independence model.

## Cycle verification (2026-09-14)

- `.venv/bin/python -m riff source validate-engineer-manifest --manifest config/engineer_sources.json` — 16 sources valid.
- `.venv/bin/python -m pytest -q tests/test_engineer_sources.py` — 4 passed.
- `.venv/bin/python -m pytest -q -m 'not postgres'` — 61 passed.
- `.venv/bin/python -m pytest -q -m postgres` against an isolated temporary PostgreSQL instance — 83 passed.
- `git diff --check` and JSON validation passed.
- No live source, social account, employer feed, or credential was accessed.

## Completion note

The user approved the proposed roster on 2026-09-14. This approval covers the
roster and source-qualification decisions only; it does not authorize live
collection. All entries remain disabled pending individual terms and retention
review before a later source-selection goal enables any feed or API.
