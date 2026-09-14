# G16 — Expand the technical-writing RSS source set

**Status:** Complete
**Depends on:** G15
**Unlocks:** G17, richer technical-writing evidence for future dogfood runs
**PRD references:** Sections 7–8, 22, 24.3, 26–29, 33

## Outcome

Riff can maintain a broad, reviewable RSS/Atom source set for applied-AI
discovery without turning unverified feeds, vendor repetition, or feed volume
into false independent evidence.

## User-visible proof

An operator can inspect the source registry, understand why each feed is
included, run the bounded fixture-backed collector, and see explicit outcomes
for valid, malformed, duplicate, unavailable, and terms-pending sources.

## Inputs

- The candidate inventory produced during G15 review: research, engineering,
  framework, observability, safety, and independent-analysis feeds.
- The G02 RSS/Atom ingestion contract and G09b source-manifest policy.
- Recorded feed responses; no live network access is required for tests.

## Scope

- Add the Tier 1 RSS/Atom inventory to the reviewed source manifest and the
  technical-writing registry, including OpenAI News, Google DeepMind, Google
  Research, Hugging Face, four relevant arXiv categories, BAIR, MIT AI News,
  AWS Machine Learning, OpenTelemetry, and the selected NIST feed(s).
- Record Tier 2 candidates separately when their endpoint or terms status is
  uncertain; do not silently enable them.
- Capture endpoint, source owner/root, artifact class, cadence, permission and
  retention status, identity fields, fixture plan, request bounds, feed quirks,
  and fallback behavior for every entry.
- Add fixture coverage for RSS 2.0, Atom, missing dates/titles, GUID-only
  permalinks, wrong content types, malformed entries, conditional requests,
  syndication, and unchanged reruns.
- Preserve the existing rule that source count is not evidence independence;
  organization roots, syndicated URLs, and arXiv version lineages remain
  correlated.

## Non-goals

- Live collection, scraping, terms approval, unofficial RSS mirrors, or adding
  credentials to configuration.
- Ranking sources by popularity or changing signal-engine thresholds.
- Engineer-specific source discovery (G17) or GitHub discovery evaluation (G18).

## Acceptance criteria

- [x] The manifest names every Tier 1 source, its canonical feed endpoint, owner,
  source root, artifact class, and current permission/terms state.
- [x] The technical-writing registry contains only secret-free, explicitly
  bounded entries; sources pending review are disabled or visibly pending.
- [x] Every source has retention, cadence, identity/provenance, fixture/replay,
  rate-limit, failure, and fallback metadata.
- [x] Fixture tests cover RSS/Atom format differences, GUID-only links, malformed
  entries, wrong content types, duplicate syndication, and safe reruns.
- [x] A reviewer can see which feeds are independent roots and which are
  correlated vendor, university, publisher, or paper-version sources.
- [x] No test requires a live network, paid provider, or source credential.
- [x] The operator notes include a dated review and a named decision for every
  unavailable, terms-pending, or noisy feed.

## Deliverables

- Updated `config/ingestion_sources.json` and `config/technical_sources.json`.
- Updated `docs/ingestion-sources.md` with the RSS inventory and enablement
  checklist.
- Any required ADR documenting feed selection, parser quirks, and correlation.
- Recorded RSS fixtures and focused ingestion tests.

## Verification

- Validate both manifests with the source validator.
- Run the offline suite and focused RSS ingestion tests.
- Report source counts by owner/root, artifact class, pending state, and fixture
  outcome; confirm that no live fetch occurs during tests.

## Handoff

Feed entries that remain terms-pending or technically noisy become explicit
inputs to G17/G18 rather than being silently substituted or promoted. Persisting
HTTP `ETag`/`Last-Modified` validators is recorded separately as
`BL-G16-001`; it is intentionally not part of this source-inventory goal.

## Cycle verification (2026-09-14)

- `.venv/bin/python -m riff source validate-manifest --manifest config/ingestion_sources.json` — valid; 5 core category sources plus 13 RSS inventory entries.
- `.venv/bin/python -m pytest -q tests/test_rss_source_expansion.py tests/test_writing_ingestion.py tests/test_ingestion_sources.py` — 16 passed.
- `.venv/bin/python -m pytest -q -m 'not postgres'` — 56 passed.
- `.venv/bin/python -m pytest -q -m postgres` against an isolated temporary PostgreSQL instance — 83 passed.
- `git diff --check` and JSON validation for both manifests passed.
- No live RSS or GitHub request was made; every source remains disabled pending operator terms/retention review.
