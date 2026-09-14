# G21 — Automate compliant job collection and listing URL intake

**Status:** Ready
**Depends on:** G04
**Unlocks:** Fresh scheduled job-market evidence and synthesis-ready listing analysis
**PRD references:** Sections 7.1, 8, 22, 24.3, 26–29, 33

## Outcome

Riff can collect job listings from explicitly configured, permitted sources on a
bounded schedule and can accept one user-submitted listing URL for fetch,
decomposition, storage, and later synthesis. Both workflows use the same
one-shot application path, preserve G04's provenance and versioning guarantees,
and fail closed when a source, URL, network target, or access method is not
approved.

This goal adds an operational seam for live collection; it does not authorize
scraping a provider whose terms, robots policy, authentication boundary, or
technical controls do not permit the selected access method. Repository source
entries should remain disabled until an operator records that review.

## User-visible proof

An operator can:

1. run a fixture-backed or explicitly enabled `riff job collect` command from a
   terminal;
2. schedule that same one-shot command from cron (or an equivalent local
   scheduler) without a second implementation path;
3. inspect run, retry, duplicate, skipped, and stored-item results; and
4. run `riff job submit-url --url <listing-url> --source-id <source-id>` to
   decompose one permitted public listing, retain its raw snapshot and
   provenance, and expose the normalized fields as inputs to the existing
   evidence/receipt pipeline.

## Inputs and boundaries

- G04's schema-versioned import format, employer identity, repost/version,
  cursor, and evidence-store contracts.
- G02's adapter, cursor, retry, run, and item-outcome contracts.
- G13's scheduled-worker and operational observability contracts.
- A source manifest containing explicit access method, terms/robots review,
  domain/URL allowlist, cadence, request bounds, retention, and fixture plan.
- Recorded HTTP/RSS/HTML/JSON-LD fixtures and an injected fetch client for all
  automated tests.

The live boundary is read-only and opt-in. It may contact only the configured
public endpoint or the one user-submitted URL after validation. It must not
follow arbitrary links, access private networks, use browser credentials, or
persist secrets.

## Scope

### 1. Source policy and manifest

- Expand the job-source configuration to schema version `2` (or add a
  versioned companion policy) with `source_id`, `source_kind` (`API`, `RSS`,
  `HTML`, or `USER_URL`), endpoint/URL patterns, permitted domains, terms and
  robots review status/date, cadence, `enabled`, retention, fixture reference,
  page/item/request/body/redirect bounds, timeout, retry policy, and stop rules.
- Reject enabled sources that lack an allowlist, review record, bounds, or
  fixture coverage. Keep credentials out of configuration and logs.
- Permit a `USER_URL` source for one-shot submissions without turning it into a
  crawl or a general job-board search.

### 2. Bounded collection command

- Add `riff job collect [--source-id ...] [--date ...] [--dry-run]` and a
  documented cron/launchd invocation.
- Reuse G04 normalization and persistence rather than creating a second job
  model. Support the selected provider's permitted API, RSS, or bounded HTML
  extraction through an injected client.
- Enforce per-run request/page/item/body/redirect/time budgets, typed retries,
  and a durable cursor. Do not advance a cursor before the corresponding raw
  evidence and item outcome are committed.
- Make retries, replay, locking/concurrency, and idempotence observable. A
  concurrent run must not duplicate a page or corrupt a cursor.

### 3. User-submitted URL intake

- Add `riff job submit-url --url <url> --source-id <source-id>` with optional
  fixture/dry-run switches for local development.
- Validate before network access: HTTP(S) only; no embedded credentials,
  localhost, loopback, link-local, multicast, private, reserved, or unsafe
  resolved addresses; host and path must match the `USER_URL` allowlist; bounded
  redirects must be revalidated at every hop; response size and timeout are
  bounded; only one listing URL is fetched.
- Prefer a `JobPosting` JSON-LD block. Use a bounded HTML fallback only when the
  source policy permits it, and never follow page links or execute page code.
- Record the submitted URL, final canonical URL, source policy/version,
  retrieval time, response metadata, parser/decomposer version, raw snapshot,
  and structured outcome/error.

### 4. Decomposition and synthesis handoff

- Normalize title, company/employer identity, seniority, compensation,
  responsibilities/description, explicit technologies, capabilities when
  explicitly stated, location, publication/expiration dates, and canonical URL
  into the G04 posting/evidence contract.
- Preserve unknown or absent values as `null`/unknown; do not infer salary,
  seniority, employer identity, or capabilities as fact.
- Apply exact repost deduplication and changed-content `VERSION_OF` linking to
  URL submissions and scheduled collection alike.
- Emit a synthesis-ready receipt input/reference. Do not generate a
  recommendation, apply to a role, or alter the user profile in this goal.

### 5. Operator workflow

- Document local one-shot execution, cron/launchd setup, environment/config
  injection, run inspection, retry/resume, disablement, rollback, and source
  review. State that cron and terminal call the identical command/path.
- Provide safe dry-run and fixture replay modes so development never requires a
  live provider, token, paid model, or network.

## Non-goals

- Broad crawling, arbitrary job-board discovery, link-following, authenticated
  or private pages, CAPTCHA/anti-bot bypass, or collection contrary to terms or
  robots policy.
- Automated applications, résumé generation, outreach, or model-generated
  recommendations.
- Filling missing fields, silently merging ambiguous employers, or treating
  one company's burst of listings as independent market evidence.
- Replacing G04's importer/evidence store or introducing a second scheduler or
  microservice.

## Acceptance criteria

- [ ] A schema-versioned manifest validates at least one explicitly bounded
  source definition and a `USER_URL` mode, including access method,
  terms/robots review, allowlist, cadence, limits, retention, fixture plan,
  retry policy, stop rules, and disabled-by-default behavior for unreviewed
  live sources.
- [ ] `riff job collect` and the documented cron/launchd command invoke the
  same one-shot service path and produce a deterministic run report with
  stored, duplicate, skipped, failed, retried, and cursor outcomes.
- [ ] Collection enforces request/page/item/body/redirect/time bounds, typed
  transient-versus-permanent failures, durable checkpoints, safe resume, and
  single-run locking/idempotence.
- [ ] `riff job submit-url` rejects disallowed schemes, hosts, resolved
  addresses, redirects, and sources before network access; a permitted URL
  fetches one listing only and records request/run/item provenance.
- [ ] JSON-LD and permitted HTML fixtures decompose into the G04 fields,
  preserve unknowns as unknown, retain raw evidence/canonical URL, and record
  parser/decomposer and policy versions.
- [ ] URL-submitted and scheduled postings share exact-repost deduplication,
  changed-content version chains, employer identity correlation, searchable
  evidence, and a synthesis-ready receipt reference.
- [ ] Replay of the same policy/input is a no-op for logical evidence while
  retaining retrieval history; a transient failure retries the same cursor and
  a permanent failure stops without cursor advancement.
- [ ] Offline tests use only recorded fixtures/injected clients and prove cron
  versus terminal equivalence; no credentials, private URLs, live requests, or
  paid model calls are required.
- [ ] Operator documentation explains terms/robots approval, dry-run, review,
  scheduling, inspection, disablement, rollback, retention, and the no-crawl/
  no-application boundary.

## Deliverables

- Versioned job-source policy/configuration (safe repository defaults remain
  disabled where live review is missing).
- Bounded fetch/client module and one-shot collection runner integrated with
  G04, plus URL validation/SSRF guard and single-listing intake module.
- CLI commands for collection, URL submission, dry-run/replay, and run/result
  inspection.
- Migrations only if G04's existing run, evidence, and retrieval records cannot
  preserve request/decomposition provenance without ambiguity.
- Recorded fixtures under `tests/fixtures/jobs/http/` and
  `tests/fixtures/jobs/url/`; focused tests such as
  `tests/test_job_collection.py` and `tests/test_job_url_intake.py`.
- README/operator documentation and an architecture note describing the shared
  cron/terminal path and safety boundary.

## Execution contract

### Canonical domain contract

Policy schema is `2`; parser/decomposer contracts are independently versioned.
Required source fields are `source_id`, `source_kind`, `enabled`, `allowlist`,
`terms_review`, `robots_review`, `cadence`, `bounds`, `retry_policy`,
`retention`, and `fixture_reference`. `source_kind=USER_URL` permits exactly
one submitted URL per invocation. Credentials are process-only.

Each collection or submission run has `run_id`, `source_id`, `policy_version`,
`mode` (`COLLECT` or `SUBMIT_URL`), `started_at`, `finished_at`, and typed
outcomes. Each item records request URL/final URL, canonical posting identity,
retrieved-at, raw snapshot reference/hash, parser/decomposer version, and
`STORED`, `DUPLICATE`, `SKIPPED`, `RETRIED`, or `FAILED` outcome. A posting's
unknown fields remain null; only `VERSION_OF` may connect changed content.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Approved API/RSS/HTML fixture | Bounded normalized postings, raw provenance, and committed cursor |
| Unreviewed/disabled source | Fail closed before network; actionable policy error |
| Unsafe scheme/host/private resolution/redirect | Reject before request or before following the redirect |
| Valid JSON-LD `JobPosting` | Parse bounded fields and store raw snapshot plus parser version |
| Permitted HTML without JSON-LD | Use bounded fallback and record fallback reason/version |
| Malformed/ambiguous listing | Preserve raw evidence and typed partial/failed outcome; do not invent fields |
| Missing compensation/seniority/date | Store null/unknown |
| Exact repost or URL replay | One logical posting/evidence version; retrieval history retained |
| Changed description | New evidence version linked with `VERSION_OF` |
| Transient timeout/rate limit | Retry same cursor within policy; no premature cursor advance |
| Permanent denial/malformed response | Stop item/source safely; preserve prior cursor |
| Bounds exhausted | Stop with explicit budget outcome; no additional request |
| Concurrent same-source run | One lock owner; other run exits/reports without duplicate writes |
| Cron versus terminal | Same service, policy, fixtures, and result semantics |

### Authority and side-effect boundaries

Tests and dry-runs are local and offline. A live run requires explicit operator
invocation and may perform only bounded, read-only requests to an approved
public source or the single submitted URL, then write Riff-local evidence/run
state. No browser session, private-network access, arbitrary link traversal,
subprocess, model call, upstream mutation, job application, or secret
persistence is allowed.

### Checkpoints, replay, and stop conditions

Persist run/policy identity, request attempt, response metadata, item fingerprint,
and durable evidence outcome before advancing a cursor. Retry only typed
transient failures up to the configured limit. Replaying the same source,
policy, input, and fixture is idempotent; a policy-version change creates a new
run. Stop on unsafe URL resolution, permanent provider denial, malformed
protocol response, exhausted bounds, or lock contention.

### Criterion-to-test map

| Criterion | Proof |
|---|---|
| Manifest validation and bounds | `test_job_policy_requires_review_allowlist_and_bounds` |
| Shared cron/terminal path | `test_collect_cli_and_scheduler_use_same_one_shot_runner` |
| Retry/checkpoint/idempotence | `test_collection_retry_cursor_and_replay` |
| SSRF/redirect/source rejection | `test_submit_url_rejects_unsafe_targets_before_fetch` |
| JSON-LD/HTML decomposition | `test_submit_url_decomposes_recorded_listing_fixtures` |
| Provenance/version/dedup handoff | `test_url_intake_reuses_job_evidence_version_contract` |
| Missing fields and malformed input | `test_job_decomposition_preserves_unknowns_and_partial_errors` |
| Offline/no-secret boundary | `test_job_collection_fixtures_require_no_network_or_credentials` |

## Verification

- Validate the source policy and fixtures offline.
- Run the focused collection and URL-intake tests, then the full offline suite.
- Run isolated PostgreSQL tests if persistence or migrations change.
- Demonstrate one fixture collection, one safe URL submission, a rejected SSRF
  target, deterministic replay, and cron/terminal equivalence.
- Run `git diff --check` and scans for credentials/private URLs.

## Handoff

Keep all live source entries disabled until their access method, terms, robots
policy, retention, and operational bounds are reviewed. This goal makes job
evidence available to the existing receipt/capability/signal pipeline; later
goals decide how synthesis and recommendations use it. Any provider-specific
adapter or source whose permissions cannot be established becomes a documented
fixture/import seam or a follow-up, not an implicit scraper.
