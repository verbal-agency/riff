# G25 — Make GitHub discovery meaningful and pipeline-integrated

**Status:** Queued
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

- [ ] A reviewed manifest can discover candidates from capability, repository,
  engineer, and organization seeds within declared request bounds.
- [ ] Candidate records retain stable identity, aliases, roots, organizations,
  author/engineer attribution, query provenance, correlation metadata, and
  uncertainty.
- [ ] Duplicate, fork, mirror, bot, popularity-only, malformed, and renamed
  cases are handled deterministically with recorded reasons.
- [ ] Discovery output remains a review queue; only explicit promotion writes a
  disabled scope to the GitHub source registry.
- [ ] A promoted fixture scope is ingested by G03 and its evidence is visible to
  the existing receipt/capability/signal pipeline with provenance intact.
- [ ] Strategy evaluation reports quality and cost metrics, and replaying the
  same manifest/fixture is idempotent.
- [ ] Operator documentation covers review, promotion, disablement, rollback,
  privacy, and live-network boundaries.

## Handoff

Report the selected discovery strategies, bounds, candidate schema, evaluation
metrics, promoted fixture scope, and any source types requiring a later adapter.
Keep user-owned project inventory and extension recommendations in G26/G27.
