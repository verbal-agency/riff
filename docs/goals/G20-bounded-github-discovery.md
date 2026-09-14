# G20 — Implement bounded GitHub topic/search discovery

**Status:** Ready
**Depends on:** G18
**Unlocks:** Reviewed GitHub source expansion and broader implementation-pattern evidence
**PRD references:** Sections 7.2, 8, 22, 24.3, 26–29, 33

## Outcome

Riff can run a bounded, replayable GitHub topic/search discovery pass seeded by
curated repositories, produce a deduplicated candidate review queue, and let
the user explicitly promote selected repositories into `config/github_sources.json`.
Discovery must improve recall without turning popularity, forks, mirrors, bots,
or search volume into independent evidence.

## User-visible proof

An operator can run one fixture-backed discovery command, inspect query/page/
retry budgets and candidate provenance, reject noisy candidates, and promote a
specific reviewed candidate without changing any other configured source.

## Inputs

- G18 benchmark and decision in `docs/github-discovery-evaluation.md`.
- G03's read-only GitHub REST fetcher, provider identity, alias, and artifact
  contracts.
- G08's relevance, novelty, independence, and popularity safeguards.
- `config/github_sources.json` curated seeds and recorded GitHub response
  fixtures.

## Scope

- Add a schema-versioned discovery policy/manifest for bounded topic and text
  queries, seed repositories, page/item limits, retry behavior, and stop rules.
- Add an injected discovery client that uses recorded responses in tests and
  the existing bounded GitHub HTTP boundary in an explicitly invoked live run.
- Normalize search candidates to stable provider repository IDs, canonical
  URLs, aliases, organization/root identity, fork/mirror flags, bot indicators,
  topics, and the query/seed that discovered them.
- Deduplicate provider IDs, canonical aliases, repeated release IDs, and
  content-equivalent candidates before ranking or review.
- Apply deterministic filters and reason codes for forks, mirrors, bots,
  popularity-only matches, archived/invalid responses, and root concentration.
- Persist or export a review queue without auto-enabling sources. Add an
  explicit operator promotion path that writes only reviewed repository scopes.
- Reuse the existing G03 collector after promotion; do not duplicate collection
  logic or broaden the default production source set.

## Non-goals

- Graph/contributor/dependency expansion, broad crawling, repository cloning,
  code execution, private repository access, or automatic promotion.
- Replacing the G03 collector or changing signal weights in G08.
- Treating stars, forks, search rank, contributor count, or activity volume as
  capability proof or independent evidence.
- Live network access in the test suite or persistence of GitHub credentials.

## Acceptance criteria

- [ ] A schema-versioned policy validates at most three query terms, two pages
  per query, six candidates per strategy, and ten requests per run, with
  explicit retry and stop rules.
- [ ] A fixture-backed command runs the selected queries through an injected
  client and emits a deterministic review queue containing query, seed,
  provider ID, canonical URL, alias/root, organization, topics, and reason
  codes.
- [ ] Candidates with duplicate provider IDs/aliases, forks, mirrors, bots,
  popularity-only matches, or root concentration receive deterministic filter
  outcomes and cannot be promoted as independent evidence.
- [ ] A rerun of the same policy, seed set, and fixture produces the same queue
  and zero duplicate candidate records; transient page failures preserve the
  page cursor for retry and permanent failures stop that query safely.
- [ ] The promotion command requires an explicit user confirmation and writes
  only the selected stable repository scope to `config/github_sources.json`,
  leaving all other candidates and source settings unchanged.
- [ ] A promoted repository is consumable by the existing G03 collector with
  stable provider identity and provenance linking the evidence back to the
  discovery run and query.
- [ ] Offline tests cover positive relevant matches, distractors, malformed
  responses, forks/mirrors, bot results, renamed repositories, duplicate
  releases, partial page failure, retry, bound exhaustion, unsupported query,
  and denied promotion cases.
- [ ] Operator documentation describes dry-run, review, promotion, disable,
  rollback, request budgets, privacy boundaries, and the no-auto-promotion rule.

## Deliverables

- `config/github_discovery.json` schema-versioned policy and query bounds.
- `src/riff/github_discovery.py` discovery policy, candidate normalization,
  deduplication, filtering, and review-queue contracts (or an equivalent
  module preserving these interfaces).
- Additive persistence/export for discovery runs and candidates, using a
  migration only if existing source/evidence tables cannot preserve run/query
  provenance without ambiguity.
- CLI commands for fixture-backed dry-run, queue inspection/export, and
  explicit promotion/disablement.
- Recorded fixtures under `tests/fixtures/github/discovery/` and focused tests
  in `tests/test_github_discovery.py` or a split integration test file.
- Updates to `README.md`, `docs/architecture.md`, and
  `docs/github-discovery-evaluation.md` with the operator workflow.

## Execution contract

### Canonical policy and domain contract

Policy schema is `1`. Required fields are `policy_id`, `query_terms`,
`seed_source_ids`, `max_pages_per_query`, `max_candidates_per_query`,
`max_requests`, `max_contributor_expansion`, `retry_limit`, `stop_rules`,
`review_required`, and `enabled`. `review_required` must remain `true` and
`enabled` defaults to `false` in repository configuration.

Each candidate has `candidate_id`, `provider_repository_id`, `full_name`,
`canonical_url`, `aliases`, `organization`, `root_id`, `topics`, `stars`,
`is_fork`, `is_mirror`, `bot_only`, `discovered_by`, `seed_source_id`,
`filter_reasons`, `review_status`, and `source_scope`. Review status is one of
`NEW`, `FILTERED`, `REJECTED`, `APPROVED`, or `PROMOTED`; only `APPROVED` may
transition to `PROMOTED`, and that transition requires an explicit user
confirmation token. A candidate may be `FILTERED` and `APPROVED` never; a
renamed repository retains one provider ID and alias history.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Valid bounded query and recorded response | Deterministic candidates with query/seed provenance |
| More than three terms, two pages, six candidates, or ten requests | Validation or terminal budget error before additional requests |
| Duplicate provider ID or canonical alias | One candidate with merged aliases and a duplicate reason |
| Fork, mirror, bot, or popularity-only match | Filtered/review-visible reason; never independent evidence |
| Renamed repository with stable provider ID | One candidate with previous URL in aliases |
| Transient page/rate-limit failure under retry limit | Retry same page; cursor does not advance until page durable |
| Permanent malformed/unsupported response | Query marked failed with structured error; no promotion |
| Same run/policy/fixture replay | Existing queue returned; no duplicate candidates or requests |
| Promotion without user confirmation | Denied; source registry unchanged |
| Confirmed promotion | Exactly one selected stable repository scope added/updated, disabled until normal source review |

### Authority and side-effect boundaries

Fixture evaluation and dry-run are local and offline. The live client may make
only bounded, read-only public GitHub API requests after an operator explicitly
invokes it; tokens remain process-only. Discovery may write local run/queue
state and a reviewed source scope, but cannot enable arbitrary candidates,
mutate upstream repositories, clone code, invoke subprocesses, or call a model.
The existing G03 collector remains the only path that stores repository
evidence after promotion.

### Checkpoints, replay, and stop conditions

Persist policy/query identity, page cursor, request attempt, response status,
and candidate fingerprint before advancing a page. Retry the same page on typed
transient/rate-limit failures up to `retry_limit`; stop the query on malformed
responses, exhausted requests, or root-concentration rules. A duplicate run
with the same policy, seeds, and fixture is a no-op. A policy-version change
creates a new discovery run without rewriting earlier queues.

### Criterion-to-test map

| Criterion | Proof |
|---|---|
| Policy bounds and validation | `test_policy_bounds_fail_closed` |
| Deterministic queue/provenance | `test_fixture_discovery_queue_is_deterministic` |
| Duplicate and contamination filters | `test_candidates_are_filtered_with_reason_codes` |
| Retry/cursor/idempotence | `test_discovery_retry_and_replay` |
| Explicit promotion boundary | `test_promotion_requires_confirmation_and_is_scoped` |
| G03 handoff/provenance | `test_promoted_scope_reuses_github_collector_contract` |
| Negative and unsupported fixtures | `test_malformed_and_unsupported_responses_stop_safely` |

## Verification

- Validate policy and queue fixtures offline with no GitHub token.
- Run focused discovery tests, then the full offline suite.
- Run PostgreSQL tests against an isolated database if persistence is added.
- Demonstrate deterministic replay, bounded request counts, and no automatic
  production-source mutation.
- Run `git diff --check` and credential/private-URL scans.

## Handoff

This goal implements only the selected bounded topic/search strategy. Graph
expansion and other discovery strategies remain alternatives in the G18 report
until separately evaluated. Promoted scopes remain subject to the same
per-source terms, retention, and enablement review as all other GitHub sources.
