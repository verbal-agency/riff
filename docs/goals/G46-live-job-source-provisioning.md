# G46 — Provision a compliant live job source and accumulate job-market history

**Status:** Queued
**Depends on:** G21, G40, G41, G43, G35
**Unlocks:** G45 (the dogfood gate runs on all three PRD inputs) and G47 (demand-side ranking needs real history)
**Canonical scenario:** `SC-LIVE-JOBS-001`

## Outcome

Riff collects real, permitted job listings on a bounded schedule from a
reviewed, enabled source, so the live daily worker has the third PRD input
(PRD §34: applied-AI job listings) rather than skipping jobs with
`NO_ENABLED_APPROVED_SOURCES`. The operator can see how many listings were
collected, how many were reposts, how many fell inside the target role family,
and how many weeks of history exist.

G21 built the compliant collection seam but deliberately stopped before
enabling any real source. This goal takes that remaining step. It does not add
a new collection mechanism, scrape sites that forbid it, or change how jobs
are ranked.

## Missing pieces this goal closes

- **No live source:** `config/job_sources.json` contains only a disabled
  placeholder (`jobs.example`, `PENDING_REVIEW`) and a user-URL intake source.
  The worker therefore collects no jobs unless the operator supplies them.
- **No yield visibility:** nothing reports whether collected listings are in
  the target role family, are reposts, or accumulate into a usable history.
- **PRD drift:** the first dogfood test assumes several weeks of job listings;
  the G41–G45 roadmap does not provide them.

## Scope

- Choose and record, in an ADR, the access path for at least one live source,
  in this order of preference: public ATS board endpoints that publish
  structured listings by design (for example per-company Greenhouse, Lever, or
  Ashby boards); a licensed aggregator API; operator-supplied exports. Record
  why each rejected path was rejected.
- Curate a bounded, versioned list of target employers (board identifiers)
  with the role-family intent for each. Keep it reviewable in configuration;
  do not discover employers at runtime.
- Complete and record the terms-of-service and robots/usage review for each
  enabled source, with date and reviewer, using the existing policy fields.
  Enable a source only after its review is recorded.
- Extend the existing `JobCollectionRunner`/`JobSourcePolicy` path to cover the
  chosen endpoint shape. Reuse G21's SSRF protection, allowlist, request/body
  bounds, retry policy, cursor, run, and item-outcome contracts. Do not create
  a second collection path.
- Add a role-family filter with a versioned, explainable rule set so listings
  outside the target family are retained as counted, labeled evidence of
  coverage but do not become capability evidence. Report included and excluded
  counts.
- Add a job-yield report: listings collected per source and run, new versus
  repost versus changed, role-family inclusion rate, employer coverage, and
  accumulated history span in days.
- Support multiple enabled job sources through G43's explicit selection rule,
  and document the recommended unattended default.
- Apply G35 retention and data-origin rules: collected listings are `LIVE`,
  retained per the source's recorded retention, and never mixed with fixtures.

## Non-goals

- Scraping or crawling any site whose terms, robots policy, authentication
  boundary, or technical controls forbid the access method. Boards such as
  LinkedIn and Indeed stay out unless a licensed or permitted API is obtained.
- Browser automation, logged-in sessions, CAPTCHA handling, proxy rotation, or
  any evasion of access controls.
- Changing capability extraction, ranking, or recommendation behavior. Ranking
  semantics belong to G47.
- Applying to jobs, résumé matching, compensation inference, or concluding
  that one employer's hiring burst is a market trend.
- Runtime employer discovery or an unbounded crawl.

## Acceptance criteria

- [ ] At least one live job source is enabled with a recorded terms and
  robots/usage review, a documented cadence, request bounds, and retention.
  An enabled source without a recorded review fails policy validation.
- [ ] A scheduled worker run with that source collects real listings through
  the existing runner and reports per-source outcomes; a source failure is
  isolated and reported without hiding other sources' yield.
- [ ] Collected listings are origin-labeled `LIVE`, deduplicated by the G04
  repost/version rules, and traceable from receipt to raw snapshot.
- [ ] Listings outside the target role family are retained and counted but do
  not produce capability mappings; the filter rule version is recorded on each
  decision.
- [ ] The job-yield report states listings per run, new/repost/changed counts,
  inclusion rate, employer coverage, and accumulated history span.
- [ ] `riff worker readiness` shows the job source as usable, empty, failed,
  or pending review, per G41's definitions, with source-specific remediation.
- [ ] Automated tests use recorded endpoint fixtures and an injected fetch
  client; none makes a live network request or embeds credentials.
- [ ] After the source is enabled, at least one explicitly recorded live
  collection run succeeds. The operator records whether the sample looks like
  the intended market (human judgment, not inferred from tests).

## Deliverables

- ADR recording the access-path decision and rejected alternatives.
- Reviewed, versioned employer/board list and the enabled source entry.
- Runner support for the chosen endpoint shape, plus the role-family filter.
- Job-yield report on the CLI and the existing read surfaces.
- Operator note covering cadence, review expiry, and what to do when a source
  changes its terms or schema.
- Focused tests and one recorded live-collection report.

## Execution contract

### 1. Decide access before writing code

Record the ADR first. If no source can be reviewed as permitted, the correct
result is an honest `blocked` report, not a weaker compliance posture. A
user-supplied export path remains a valid, documented fallback and must keep
working.

### 2. Reuse the existing collection path

Extend `job_source_policy.py`, `job_fetch.py`, and `job_collection.py` rather
than adding a parallel collector. Preserve schema-versioned policy validation;
bump the policy schema only if a new field is genuinely required, and keep the
existing placeholder and user-URL entries valid.

### 3. Keep filtering separate from collection

The role-family filter decides what becomes capability evidence, not what is
stored. Retained out-of-family listings let the operator audit the filter and
tune it without recollecting. Record the filter version on every decision so
changing it is reversible and replayable through G43's origin-safe replay.

### 4. Make history measurable from day one

G47 will judge demand trends over time, so every collected listing must carry a
reliable first-seen and last-seen timestamp and stable employer and posting
identity. Do not backfill or fabricate history; a short history is reported as
short.

### 5. Verify and report

Run the focused tests, then one explicit live collection after review is
recorded. State which acceptance criteria are automated and which are the
operator's judgment about sample representativeness.
