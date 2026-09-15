# G25 — Make GitHub discovery meaningful and pipeline-integrated

**Status:** Complete
**Depends on:** G18, G20, G22
**Unlocks:** User-relevant GitHub evidence and project understanding
**PRD references:** Sections 7.2, 7.4, 8, 21–22, 24.3, 27, 33
**Canonical scenario:** `SC-GITHUB-DISCOVERY-002`

## Outcome

Riff can discover GitHub repositories and public engineering activity that are
meaningful for the user's interests, not merely popular search results. Every
candidate remains bounded, deduplicated, provenance-bearing, and reviewable;
approved candidates can enter the existing G03 collection and downstream
receipt, capability, signal, and Riff pipeline.

Discovery remains separate from automatic collection. A candidate never becomes
a production source without an explicit user decision.

## User-visible proof

The user can provide capability terms, seed repositories, named engineers, or
organizations and receive a ranked review queue explaining why each candidate
was found, how it relates to the seed, what evidence is available, and whether
it is safe to promote into collection.

## Scope

### 1. User-relevant discovery inputs

- Add a versioned, secret-free discovery manifest supporting capability terms,
  curated repository seeds, public engineer/organization seeds, and bounded
  topic/search queries.
- Define explicit limits for query count, pages, candidates, requests,
  contributor or related-project expansion, retries, and retention.
- Keep discovery disabled until the operator reviews privacy, terms, and source
  scope; public GitHub metadata is the default boundary.

### 2. Candidate quality and provenance

- Preserve stable provider repository IDs, canonical URLs, aliases, owners,
  organizations, authors, forks/mirrors, roots, query/seed provenance, and
  correlation metadata before review.
- Deduplicate renames, aliases, forks, mirrors, syndicated artifacts, and
  repeated releases before ranking relevance.
- Treat stars, forks, search rank, and activity volume as context only; they
  cannot independently establish capability relevance.
- Record deterministic relevance reasons, uncertainty, and a review status for
  every candidate.

### 3. Review and collection integration

- Retain the existing `NEW -> APPROVED -> PROMOTED` review boundary and require
  an explicit promotion token.
- Promote only a stable, disabled GitHub source scope into
  `config/github_sources.json`, carrying discovery-run and seed provenance.
- Verify promoted scopes use the existing bounded G03 collector and become
  searchable evidence, receipts, normalized capabilities, and signal inputs.
- Do not silently broaden an existing source or enable a live scope.

### 4. Evaluation and operations

- Compare at least curated, topic/search, and seed-linked strategies using
  precision, recall, duplicate/correlation rate, root/organization diversity,
  contamination, request volume, and replay safety.
- Add recorded responses and negative fixtures for irrelevant popularity,
  bot/fork/mirror contamination, renamed repositories, and malformed results.
- Document fixture replay, review, promotion, disablement, rollback, and live
  opt-in commands.

## Non-goals

- Broad crawling, repository cloning, code execution, private-repository access,
  or credential persistence.
- Automatic source promotion, automatic collection enablement, or autonomous
  conclusions about the user's skill.
- Replacing G03/G20 collectors or introducing a graph database.

## Acceptance criteria

- [x] A reviewed manifest can discover candidates from capability, repository,
  engineer, and organization seeds within declared request bounds.
- [x] Candidate records retain stable identity, aliases, roots, organizations,
  author/engineer attribution, query provenance, correlation metadata, and
  uncertainty.
- [x] Duplicate, fork, mirror, bot, popularity-only, malformed, and renamed
  cases are handled deterministically with recorded reasons.
- [x] Discovery output remains a review queue; only explicit promotion writes a
  disabled scope to the GitHub source registry.
- [x] A promoted fixture scope is ingested by G03 and its evidence is visible to
  the existing receipt/capability/signal pipeline with provenance intact.
- [x] Strategy evaluation reports quality and cost metrics, and replaying the
  same manifest/fixture is idempotent.
- [x] Operator documentation covers review, promotion, disablement, rollback,
  privacy, and live-network boundaries.

## Handoff

Report the selected discovery strategies, bounds, candidate schema, evaluation
metrics, promoted fixture scope, and any source types requiring a later adapter.
Keep user-owned project inventory and extension recommendations in G26/G27.

## Current implementation slice (2026-09-14)

- Extended `DiscoveryPolicy` with bounded capability, repository, engineer, and
  organization inputs plus an explicit `max_queries` bound while preserving the
  G20 `query_terms` shape.
- Candidate queues now retain seed kind/value, authors, correlation metadata,
  deterministic relevance reasons, uncertainty labels, and stable review
  scores. Promotion carries this provenance into a disabled
  `config/github_sources.json` scope.
- Added `config/github_discovery_seed_example.json` and
  `tests/fixtures/github/discovery/seed-responses-v1.json` for offline replay,
  including duplicate, rename, attribution, and malformed-result cases.
- Verification: `.venv/bin/python -m pytest -q tests/test_github_discovery.py`
  (9 passed); the full offline suite remains green.
- G25's promoted fixture scope is now exercised through the real G03/Postgres
  pipeline. The test enables only a uniquely isolated fixture source; no live
  GitHub requests or checked-in source enablement were performed.

## Completed integration contract

This cycle proves that the existing discovery review boundary feeds the
existing G03 collector; it does not redesign discovery or enable a live source.

### Expected implementation surface

- `src/riff/github_discovery.py`: preserve `promote_candidates`; make only
  additive provenance or validation changes if integration exposes a gap.
- `src/riff/cli.py`: reuse `sources sync` and `ingest --source-type GITHUB`;
  do not add a second GitHub collection command unless the report names the
  compatibility reason.
- `tests/test_github_discovery.py`: retain review/promotion and malformed-case
  coverage.
- `tests/test_github_ingestion.py` (Postgres): add the promotion-to-collection
  proof using recorded discovery and collector fixtures.
- `tests/fixtures/github/discovery/`: record the exact promoted candidate and
  registry projection used by the integration test.
- `docs/reports/g25-github-integration.md`, `README.md`, and
  `docs/architecture.md`: document offline replay, review/promotion, registry
  sync, collection, disablement, and rollback commands.

### Canonical contracts and invariants

- Discovery queue schema remains version `1`; candidate identity is the stable
  `provider_repository_id`, with aliases and `root_id` retained.
- Review transitions remain `NEW -> APPROVED -> PROMOTED`; filtered, rejected,
  unknown, or duplicate candidates cannot be promoted.
- Promotion requires the literal operator confirmation `PROMOTE`, writes a
  disabled `GITHUB` source with `permission_status=PENDING_REVIEW`, and carries
  `discovery_run_id`, `discovered_by`, authors, correlation metadata, and
  uncertainty into registry/source metadata.
- `riff sources sync` is the only registry-to-Postgres projection. Collection
  uses `GitHubIngestionRunner` through the G03 `riff ingest --source-type GITHUB`
  path and persists evidence, repository identity, artifact metadata, run/item
  outcomes, and cursors in the canonical store.
- Promotion never enables a source, and a disabled source produces
  `SKIPPED/SOURCE_DISABLED` with zero evidence writes. No private repository,
  arbitrary URL, direct SQL from discovery, or inferred authorship is allowed.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Valid reviewed candidate + `PROMOTE` | One disabled registry entry with discovery provenance; queue status `PROMOTED` |
| Missing/wrong confirmation, filtered, rejected, or unknown candidate | Typed refusal; registry and queue unchanged |
| Sync promoted registry | One `GITHUB` source with preserved metadata; repeat sync is idempotent |
| Collect while source disabled | `SKIPPED/SOURCE_DISABLED`; zero evidence/artifact rows |
| Explicitly enabled fixture scope | G03 stores searchable evidence and artifacts with source, author, organization, root, and discovery provenance |
| Repeat unchanged collection | `stored=0`, duplicate outcomes only, unchanged evidence count |
| New fixture release/README version | One new version linked to prior evidence; cursor advances after durable item commit |
| Malformed, rate-limited, or mid-page fixture response | Typed partial/permanent outcome; no cursor skip; retry/replay is idempotent |

### Authority, side effects, and replay boundaries

- Discovery fixture replay and Postgres integration may write only the test
  database and temporary queue/registry files. Live GitHub requests require an
  explicit `--live` policy and remain outside acceptance evidence.
- The operator alone approves candidates and enables a promoted source; neither
  a model response nor a fixture can satisfy either authority boundary.
- Credentials stay in environment variables and never enter fixtures, logs, or
  registry metadata. The collector is read-only against GitHub and bounded by
  page, byte, retry, and content limits.
- Replaying the same manifest, promotion, sync, or collection must not create
  duplicate source, repository, artifact, evidence, or provenance records.

### Criterion-to-proof map

| G25 criterion | Required proof |
|---|---|
| Promoted scope enters G03/Postgres with provenance | `test_promoted_fixture_scope_reuses_g03_pipeline` |
| Review/promotion safety and metadata | Existing `test_review_and_promotion_require_explicit_transitions` plus registry assertions |
| Duplicate/rename/fork/bot handling | Existing discovery tests plus `test_repository_rename_preserves_identity` and `test_related_repository_flags_are_retained` |
| Replay/idempotence and cursor safety | `test_github_three_passes`, `test_rate_limit_preserves_cursor_until_retry`, and `test_mid_page_termination_replays_without_missing_items` |
| Operator/privacy boundary | CLI/docs report, `git diff --check`, and no-live-network fixture run |

The goal is complete: the promoted fixture scope was enabled explicitly in an
isolated Postgres test, collected through G03, and verified as searchable with
discovery metadata intact.
