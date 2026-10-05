# G43 — Make live evidence produce useful recommendations

**Status:** Complete
**Depends on:** G40, G41, G05, G06, G21, G30
**Unlocks:** Reliable live recommendation dogfooding and G42 provider-backed publication
**Canonical scenario:** `SC-LIVE-DAILY-001`

## Outcome

The live worker can turn successfully collected real-world evidence into
grounded capability candidates and recommendations. Source failures remain
visible and isolated, while an operator can replay already-stored live
evidence after improving extraction or normalization without refetching the
network.

## Scope

- Replace the live worker's smoke-only `KeywordExtractor` path with a
  versioned, candidate-producing extractor. Keep the deterministic smoke
  extractor available for fixture tests and explicitly label both paths.
- Extract capability candidates, technology candidates, claims, relevant
  spans, and uncertainty from realistic RSS, GitHub, and job evidence without
  inventing unsupported claims.
- Add an origin-safe replay path for persisted `LIVE` evidence. Replay must
  reuse raw evidence, preserve provenance, create new extractor/normalizer
  attempts, and never fetch or mutate source cursors.
- Make RSS and GitHub source failures isolate per source, classify rate limits
  and permanent feed errors, and report healthy-source yield separately from
  failed-source yield.
- Give the scheduled worker an explicit job-source selection/default so
  multiple enabled job sources do not silently result in no job collection.
- Distinguish valid empty days from extraction failures, source-unavailable
  days, and insufficient-evidence days in the durable run report.
- Keep the provider-neutral reasoning boundary intact; provider-backed
  generation remains G42.

## Non-goals

- Calling a paid model or selecting a specific hosted model provider.
- Treating source volume as independent evidence or promoting unreviewed
  sources automatically.
- Refetching live sources as part of replay, rewriting raw evidence, or
  allowing fixture/test rows into a live result.
- Building a general-purpose document understanding platform.

## Acceptance criteria

- [x] A realistic recorded live-shaped input produces at least one valid
  receipt, one capability or technology mapping, one ranked candidate, and a
  provenance-linked deterministic Riff.
- [x] A replay of persisted `LIVE` evidence produces the same bounded result
  without network calls, cursor changes, fixture contamination, or duplicate
  raw evidence; the new extractor/normalizer versions are visible.
- [x] The live extractor is not the smoke extractor and has positive and
  negative tests for capability phrases, technologies, claims, spans, and
  uncertainty.
- [x] RSS, GitHub, and jobs report per-source stored, duplicate, skipped,
  transient, permanent, and rate-limit outcomes; one failing source does not
  erase healthy-source evidence.
- [x] Multiple enabled job sources require an explicit selector or documented
  default, and the selected source can be collected through both terminal and
  scheduled paths.
- [x] The worker classifies `SUCCEEDED`, `PARTIAL`, valid `EMPTY`,
  `INSUFFICIENT_EVIDENCE`, and `EXTRACTION_FAILURE` distinctly, with an
  actionable remediation in the report.
- [x] Offline and Postgres tests cover replay isolation, provenance/origin
  boundaries, source failure isolation, job selection, idempotence, and the
  end-to-end candidate-to-Riff path.

## Deliverables

- Versioned live extractor and replay command/service.
- Source-health and extraction-yield report fields.
- Explicit job-source selection/default configuration.
- Recorded live-shaped fixtures, failure fixtures, and Postgres assertions.
- Updated operator documentation with one-line fetch and replay commands.

## Execution contract

Reuse `ReceiptProcessor`, `EvidenceRepository`, `NormalizationService`,
`SignalRanker`, and `DailyRiffService`; the new live extractor remains behind
the existing receipt-extractor protocol. The replay command must select only
`LIVE` evidence, accept an explicit lower-bound timestamp and maximum item
count, and never invoke a source fetcher or advance a cursor. `--job-source-id`
is the only new source-selection override; it cannot enable a disabled or
unreviewed source. Tests use recorded RSS-shaped evidence and Postgres rows;
no paid provider or live network is required.

## Verification evidence

- `.venv/bin/python -m pytest -q -m 'not postgres'` — 144 passed.
- `RIFF_DATABASE_URL=... .venv/bin/python -m pytest -q tests/test_live_worker.py` — 3 passed.
- The focused Postgres path proves candidate extraction, network-free LIVE
  replay, and publication from two recent independent source types.
- `riff worker --replay-live --date 2026-10-01 --since 2026-10-01T00:00:00+00:00`
  selected persisted LIVE evidence without refetching; the result remained
  honestly empty because surviving evidence scored below the publication
  threshold.
- `git diff --check` and Python compilation pass.

The complete Postgres suite still has the pre-existing connector promotion
failure in `tests/test_connector.py::test_http_connector_runs_read_promote_export_against_persisted_postgres`; the focused G43 Postgres tests pass.
