# G18 — Evaluate the GitHub discovery process

**Status:** Ready
**Depends on:** G15
**Unlocks:** A bounded GitHub discovery implementation goal
**PRD references:** Sections 7.2, 8, 22, 24.3, 26–29, 33

## Outcome

Riff has an evidence-backed answer to how it should discover useful GitHub
repositories, projects, contributors, and implementation patterns beyond its
current explicit repository scopes.

## User-visible proof

An operator can see the current GitHub discovery funnel, compare bounded
discovery strategies, understand their precision/recall and bias tradeoffs, and
approve a concrete next implementation slice without broad crawling.

## Inputs

- The completed G03 explicit-repository collector and its identity contracts.
- The G08 independence, novelty, relevance, and popularity safeguards.
- Recorded GitHub API fixtures, including repositories, topics, releases,
  contributors, issues/discussions, dependencies, forks, mirrors, and bots.

## Scope

- Map the current process from configured repository to stored evidence and
  identify where discovery is absent, manual, popularity-biased, or duplicative.
- Compare at least three bounded strategies: curated repository scopes, GitHub
  search/topic queries, and graph expansion from known repositories or
  contributors. Consider release/activity and dependency signals separately.
- Build an offline benchmark with known relevant repositories, distractors,
  forks/mirrors, bots, popular-but-irrelevant projects, renamed repositories,
  and duplicate/syndicated evidence.
- Measure precision@k, recall of seeded relevant projects, duplicate rate,
  organization/root diversity, bot/fork contamination, request volume, and
  cursor/retry behavior for each strategy.
- Define query bounds, stop conditions, rate-limit handling, privacy limits,
  and the approval boundary for promoting a discovered scope into collection.
- Produce a recommendation for the smallest useful next implementation goal.

## Non-goals

- Broad crawling, unaudited live search, executing repository code, or changing
  the current GitHub collector in this evaluation goal.
- Treating stars, forks, search rank, or contributor count as independent
  evidence or capability proof.
- Automatically adding discovered repositories to production collection.

## Acceptance criteria

- [ ] A process map and gap analysis describe current explicit-scope discovery,
  its blind spots, and its operational limits.
- [ ] At least three discovery strategies are evaluated against the same
  deterministic benchmark fixture.
- [ ] The report includes precision@k, recall, duplicate/root-correlation,
  diversity, contamination, request-volume, and retry metrics.
- [ ] Fixtures demonstrate safe handling of forks, mirrors, bots, renames,
  popularity-only changes, and repeated release syndication.
- [ ] A bounded query and promotion policy specifies page/item limits,
  rate-limit behavior, privacy constraints, and human approval requirements.
- [ ] The report recommends one next implementation slice or explicitly records
  that discovery should remain curated/manual.

## Deliverables

- `docs/github-discovery-evaluation.md` process map, benchmark, and decision.
- Recorded GitHub discovery fixtures and a reproducible evaluation command.
- A proposed discovery manifest/query schema, if the evaluation recommends
  implementation.
- A follow-up goal or backlog item for the selected strategy.

## Verification

- Run the benchmark entirely against recorded fixtures with no live GitHub
  request and no token.
- Re-run it to confirm deterministic metrics and stable repository identity.
- Confirm the evaluation cannot mutate target repositories or production source
  configuration.

## Handoff

Only the bounded strategy selected by the report may become a later
implementation goal; all other discovery ideas remain explicit alternatives.
