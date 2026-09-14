# GitHub discovery evaluation (G18)

**Benchmark:** `g18-github-discovery-v1`
**Date:** 2026-09-14
**Fixture:** `tests/fixtures/github/discovery-benchmark-v1.json`

## Process map

The current production path is deliberately curated:

```text
config/github_sources.json
  -> source sync into Postgres
  -> explicit repository endpoint
  -> read-only GitHub REST fetcher
  -> bounded repository/releases/issues/README collection
  -> provider-ID/content-hash deduplication and evidence storage
  -> receipts, capabilities, and signal ranking
```

`config/github_sources.json` currently contains no enabled production scopes.
The G03 collector can ingest an explicit repository when an operator configures
one, but it does not discover repositories from search, topics, contributors,
dependencies, releases, or related projects. The test fixtures exercise the
collector contract only; they are not a discovery corpus.

## Gap analysis

| Gap | Consequence | Guardrail needed |
|---|---|---|
| No discovery input beyond explicit repository URLs | Useful projects outside the curated list are invisible | Add a bounded, reviewable candidate queue |
| Search rank, stars, and forks are not evidence of capability | Popular but irrelevant projects can dominate results | Treat popularity as a weak feature and require relevance review |
| Provider IDs and aliases are only resolved after collection | Renames, forks, mirrors, and copies can be double-counted during discovery | Resolve stable IDs and root/correlation metadata before promotion |
| Contributor/graph expansion follows dense neighborhoods | One organization or repository can consume the request budget | Bound expansion depth and contributor count; stop on root concentration |
| No promotion boundary exists for discovered scopes | A future adapter could silently broaden collection | Require an operator decision before writing `config/github_sources.json` |

## Strategies evaluated

All strategies were evaluated against the same ten-candidate fixture and the
same five seeded relevant repositories.

1. **Curated scopes** — return only explicitly selected repositories. This is
   the precision baseline and uses no search requests.
2. **Bounded topic/search queries** — issue a small set of topic or text
   queries, inspect bounded pages, then deduplicate and rank candidates for
   review. This is the recommended next slice.
3. **Graph expansion** — expand from a known repository through contributors,
   related repositories, or dependency/release links. This remains an
   alternative, not a production strategy.

## Benchmark metrics

- `precision_at_k`: relevant seeded repositories in the first `k` results,
  divided by `k`.
- `recall_at_k`: relevant seeded repositories in the first `k` results,
  divided by all five seeded relevant repositories.
- `duplicate_or_correlated_rate_at_5`: first-five results that repeat a root
  or declare a duplicate/syndication relation.
- `root_diversity_at_5` and `organization_diversity_at_5`: unique roots or
  organizations divided by five.
- `bot_fork_contamination_at_5`: first-five results flagged as bot-only, fork,
  or mirror.
- `syndication_duplicate_rate_at_5`: first-five results with an explicit
  duplicate relation.
- `request_volume`, `pages_examined`, `retry_count`, and `cursor_replays` are
  recorded strategy costs and replay behavior, not estimates.

## Results

| Strategy | P@3 | P@5 | R@3 | R@5 | Duplicate/correlated | Root diversity | Org diversity | Bot/fork/mirror | Requests | Retries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Curated scopes | 1.0000 | 1.0000 | 0.6000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 | 5 | 0 |
| Bounded topic/search | 0.6667 | 0.8000 | 0.4000 | 0.8000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 | 6 | 1 |
| Graph expansion | 0.3333 | 0.4000 | 0.2000 | 0.4000 | 0.6000 | 0.4000 | 0.8000 | 0.6000 | 8 | 2 |

The graph strategy returns a fork, bot mirror, and syndicated mirror of the
same runtime root in its first five results. The fixture also includes a
renamed repository with one stable provider ID and two popularity-only
distractors; these remain distinct in the report and do not become independent
evidence.

## Bounded discovery and promotion policy

The next implementation may use the following limits from the fixture:

- At most three query terms per run, two pages per query, six candidates per
  strategy, and ten total requests.
- At most two contributor/related-repository expansions; stop when the root or
  organization concentration threshold is reached.
- Preserve provider repository ID, canonical URL, alias history, organization,
  fork/mirror flags, and bot author metadata before a candidate enters review.
- Deduplicate provider IDs, canonical aliases, repeated release IDs, and
  content-equivalent copies before calculating relevance or recall.
- Treat stars, forks, search rank, contributor count, and activity volume as
  context only. They cannot independently promote a repository.
- Retry only typed transient/rate-limit failures; leave cursors unchanged when
  a page is incomplete. A permanent malformed response is recorded and the
  query stops without broadening scope.
- Discovery output is a review queue. Only the user may promote a candidate to
  `config/github_sources.json`; discovery never mutates production source
  configuration automatically.
- Use public repository metadata only. Do not execute repository code, clone or
  mirror repositories, inspect private repositories, or persist credentials.

## Proposed query and candidate schema

The selected implementation should use schema version `1` with a policy record
containing `policy_id`, `query_terms`, `seed_source_ids`,
`max_pages_per_query`, `max_candidates_per_query`, `max_requests`,
`max_contributor_expansion`, `retry_limit`, `stop_rules`, `review_required`,
and `enabled`. Each discovered candidate should retain
`provider_repository_id`, `canonical_url`, `aliases`, `organization`,
`root_id`, `topics`, `is_fork`, `is_mirror`, `bot_only`, `discovered_by`,
`seed_source_id`, `filter_reasons`, and a review status. The only legal path to
production collection is `NEW -> APPROVED -> PROMOTED`, with the final
transition requiring an explicit user decision and writing one stable scope to
`config/github_sources.json`.

## Decision and next slice

Keep curated scopes as the precision baseline and implement **bounded
topic/search discovery with curated seeds** next. The implementation should
produce a deterministic candidate review queue with duplicate/root filters,
stable identity handling, explicit request bounds, and a user-controlled
promotion command. Graph expansion remains an explicitly documented
alternative until a separate benchmark shows that its contamination can be
reduced without exceeding the same privacy and request budget.

The reproducible evaluation command is:

```sh
.venv/bin/python -m riff github evaluate-discovery \
  --file tests/fixtures/github/discovery-benchmark-v1.json
```

The command reads only the recorded fixture and emits the same JSON metrics on
every run. It does not instantiate the GitHub HTTP client and cannot mutate
`config/github_sources.json` or a target repository.

## G20 operator workflow

The implementation keeps discovery output in a review queue before any source
registry change. Run the fixture path locally with:

```sh
uv run riff github discover \
  --policy config/github_discovery.json \
  --fixture tests/fixtures/github/discovery/search-responses-v1.json \
  --output /tmp/riff-github-queue.json
uv run riff github queue --file /tmp/riff-github-queue.json
uv run riff github review --file /tmp/riff-github-queue.json --candidate-id repo:5001 --apply
uv run riff github promote --queue /tmp/riff-github-queue.json \
  --candidate-id repo:5001 --confirm PROMOTE --apply
```

The promotion step writes a disabled scope with discovery run/query metadata;
it does not enable collection. A live run requires both `--live` and an
`enabled` policy whose source terms, privacy, request bounds, and retention
have been reviewed. No live request or token is required by tests.
