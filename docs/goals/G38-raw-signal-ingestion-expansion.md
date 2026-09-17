# G38 — Expand the raw-signal ingestion base

**Status:** Ready
**Depends on:** G02, G03, G05, G16, G17, G19, G20, G21, G25, G31, G34
**Unlocks:** Broader, better-grounded inputs for conversational riffing
**Canonical scenario:** `SC-RAW-SIGNAL-001`

## Outcome

Riff can collect and preserve a broader set of raw signals relevant to
operational AI reliability and executable scientific methods without pretending
that a source synthesis is independent evidence. The conversational layer may
then investigate, compare, and riff on those signals; ingestion does not need to
generate a curriculum or project automatically.

## Scope

- Add reviewed source classes for incident reports/postmortems, agent
  trajectory and observability writing, reliability/security research,
  primary scientific papers, paper-linked code and datasets, benchmarks,
  engineering blogs, changelogs, and GitHub issues/PRs/discussions.
- Extend the source registry and cron/terminal ingestion paths with stable
  source identity, author/organization, publication date, canonical root,
  linked paper/repository/dataset, version or commit, and retrieval metadata.
- Preserve raw payloads and compact Evidence Receipts separately; mark
  user-supplied summaries and secondary syntheses as leads rather than
  independent evidence.
- Apply existing deduplication, correlation, source-type, fixture, retention,
  and provenance-quality policies. A larger source count must not inflate
  independence or confidence.
- Provide fixture-backed and live-disabled validation for each new source class;
  no model call is required merely to ingest or store a source.

## Non-goals

- Automatically generating curriculum, project plans, or PRDs from one source.
- Crawling arbitrary sites, bypassing robots/terms, private repository access,
  or executing paper code.
- Treating source popularity, citation count, or repository stars as proof of a
  capability.

## Acceptance criteria

- [ ] Fixture-backed ingestion covers at least one incident/postmortem source,
  one primary paper with linked code/data, one benchmark or changelog, and one
  GitHub discussion/issue surface.
- [ ] Every stored item preserves source type, author/organization (when
  available), canonical root, publication/observed time, linked artifact
  identity, version/commit (when applicable), and provenance policy metadata.
- [ ] User-supplied or secondary summaries are stored as leads with bounded
  uncertainty and cannot count as independent roots without source validation.
- [ ] Reposts, mirrors, paper/code duplicates, and correlated sources remain
  linked and do not inflate confidence or priority.
- [ ] Cron and terminal paths share idempotent behavior, bounded requests,
  fixture replay, failure classification, and origin/retention policy.
- [ ] Offline and Postgres tests cover malformed metadata, duplicate/correlated
  inputs, provenance disclosure, fixture ownership, retry/permanent failures,
  and restart safety.
- [ ] A source-coverage report shows the new classes separately from existing
  RSS/GitHub/job sources and exposes remaining gaps without synthesizing a
  recommendation.

## Execution contract

Additive source manifests/adapters and migrations only; reuse the existing
Evidence Receipt and provenance contracts. Keep full raw bodies out of the
model-facing context by default. The next goal, G39, owns retrieval and token
budgets; G38 owns getting trustworthy raw signals into the ledger.
