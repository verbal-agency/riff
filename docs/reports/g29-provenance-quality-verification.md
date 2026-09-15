# G29 provenance-quality verification

Date: 2026-09-15

## Result

G29 is implemented. Candidate relevance (`candidate_score`), generated
confidence (`confidence`), evidence quality, and epistemic confidence are now
separate persisted/read fields. The versioned policy is
`provenance-policy-v1`.

## Policy evidence

`riff.provenance.assess_provenance` evaluates bounded receipt projections. It
counts independent roots, source types, organizations, authors, citation
completeness, duplicate content, repost markers, fixture status, and
counterevidence independently. Unknown metadata is retained as a limitation.
Deterministic states and ceilings are:

| State | Epistemic ceiling | Promotion |
| --- | ---: | --- |
| `FIXTURE_ONLY` | 0.20 | blocked |
| `SINGLE_SOURCE` | 0.55 | blocked |
| `CONTRADICTORY` | 0.45 | blocked |
| `INSUFFICIENT` | 0.20 | blocked |
| `SUPPORTED` | 0.95 | only with complete, diverse provenance |

Fixture URLs/metadata are explicitly labelled synthetic and cannot be treated
as production evidence. Repeated receipts sharing a root or content hash do
not create independent corroboration.

## Interface and persistence evidence

- Migration `016_provenance_quality` adds candidate score, evidence quality,
  epistemic confidence, policy version, and a bounded provenance summary to
  `riffs`, with legacy defaults for backward-compatible reads.
- API investigation responses include `score`, `evidence_quality`,
  `epistemic_confidence`, `confidence_policy_version`, `promotion`, and
  `provenance_quality`; the MCP adapter returns the same compact fields.
- Investigation evidence remains receipt-traceable, includes source identity,
  and caps raw evidence at 4,000 characters with an explicit truncation flag.
- Decision history remains append-only and is returned alongside the
  recalculated quality summary.

## Verification

- Offline provenance matrix: 4 tests passed (fixture-only, single-source
  volume, independent roots/diversity, contradiction/reposts).
- Full offline suite: passed; the existing warning count is limited to the
  pre-existing Starlette/httpx deprecations.
- Postgres/Docker Desktop: migration applied; daily persistence, API
  investigation, adapter fields, idempotent daily runs, and restart-safe
  conversation tests passed (`6 passed`).

The user's supplied durable-execution review is the human evaluation: it
correctly separated an interesting hypothesis from a well-supported claim and
identified the next provenance needed. The fixture-only investigation now
surfaces that same distinction in machine-readable form instead of presenting
the generated 95% score without qualification.
