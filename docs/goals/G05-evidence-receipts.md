# G05 — Produce compact, versioned Evidence Receipts

**Status:** Complete
**Depends on:** G02, G03, G04  
**Unlocks:** G06  
**PRD references:** Sections 8.2, 21, 24.1, 28–29

## Outcome

Each new raw evidence version can be processed once into a compact, structured Evidence Receipt containing grounded summary, spans, candidate capabilities and technologies, claims, and signal-strength metadata. Results are cached by content and extractor version and remain traceable to raw evidence.

## User-visible proof

An operator can inspect a receipt, follow every extracted claim or relevant span back to its evidence record and source text, and rerun processing without paying to reprocess unchanged content.

## Inputs

- Versioned raw evidence from the three G02–G04 source categories.
- A hand-labeled cross-source extraction corpus and a replaceable structured-model client.

## Scope

- Define the receipt schema and extraction service boundary.
- Represent summary, relevant spans, capability candidates, technology candidates, claims, signal strength, source metadata, content hash, extractor/model version, processing status, and uncertainty.
- Distinguish observation/claim text from later hypotheses and recommendations.
- Validate structured model output and retain explicit failures for retry or review.
- Cache results by raw content hash plus extractor/prompt/schema version.
- Support deterministic fake and recorded-fixture extraction.
- Build a hand-labeled cross-source fixture set for jobs, GitHub material, and technical writing.

## Non-goals

- Canonical capability merging, candidate trend ranking, Riff argument construction, or embeddings/vector infrastructure.
- Repeatedly passing full raw evidence into downstream stages once a valid receipt exists.

## Required properties

- Claims and spans cannot cite text outside the associated raw evidence.
- Unsupported or malformed extraction output is rejected or explicitly marked uncertain; it is not silently repaired into invented evidence.
- Reprocessing occurs only when content or extractor version changes, or an operator explicitly requests it.
- Model-provider details do not leak into domain contracts.
- The extraction path can use a cheaper model independently from later deep reasoning.

## Deliverables

- Receipt schema, migration, persistence, and retrieval.
- Replaceable structured extraction interface and at least one implementation seam.
- Validation, cache/version, retry, and processing-status behavior.
- Hand-labeled fixture corpus with an evaluation command and human-readable report.
- Batch/one-shot commands for pending evidence.

## Acceptance criteria

- [x] Representative items from all three source types produce schema-valid receipts with correct evidence IDs and source metadata.
- [x] Every extracted relevant span resolves to a valid location or exact excerpt in the stored raw evidence.
- [x] A second run over unchanged evidence and extractor version performs zero extraction calls.
- [x] Changing the extractor version produces a new receipt version while retaining the prior one.
- [x] Malformed, missing-field, out-of-source-span, and transient-provider responses have tested, inspectable outcomes and safe retry behavior.
- [x] The evaluation report scores capability, technology, organization/company, claim, metadata, and span extraction separately.
- [x] Downstream receipt retrieval does not require loading the raw body unless explicitly requested.

## Verification evidence

Run the labeled fixture evaluation with a deterministic extractor and, if configured, an optional live extractor. Record cache call counts across unchanged and version-changed reruns, plus validation failures for an intentionally hallucinated span.

## Implementation latitude

Exact quality thresholds should be baselined here rather than invented without data. The report must expose per-field errors so later work can set justified gates. Avoid optimizing a single aggregate score that hides provenance failures.

## Execution contract (satisfied in this cycle)

### Expected implementation surface

Extend `src/riff` with receipt dataclasses/schema validation, a replaceable
structured-extraction client, cache-aware receipt persistence, and a bounded
one-shot processor for pending evidence. Add migration `006_evidence_receipts.sql`,
focused tests in `tests/test_evidence_receipts.py`, and a labeled corpus under
`tests/fixtures/receipts/`. Add an evaluation command/report and document the
operator path in `README.md` plus `docs/architecture.md` (or a receipt note).
Equivalent paths are acceptable when the completion report names them.

### Canonical domain and persistence contract

Use receipt schema version `1` and preserve raw-evidence identity:

| Concept | Required fields | Invariants |
|---|---|---|
| Evidence receipt | `receipt_id`, `evidence_id`, `content_hash`, `extractor_version`, `schema_version`, `status`, `summary`, `relevant_spans`, `capability_candidates`, `technology_candidates`, `claims`, `signal_strength`, `source_metadata`, `uncertainty` | One receipt is tied to exactly one evidence version; every span is bounded by that evidence. |
| Relevant span | `start`, `end`, `excerpt` (or exact locator) | Off-source, reversed, or mismatched spans are rejected; offsets use one documented text encoding. |
| Claim | `text`, `span_ids`, `claim_type`, `uncertainty` | Claims cannot cite missing spans or become hypotheses/recommendations in this goal. |
| Processing attempt | `attempt_id`, `evidence_id`, `extractor_version`, `status`, `error_code`, `started_at`, `finished_at` | Terminal states are `SUCCEEDED`, `FAILED_VALIDATION`, `FAILED_TRANSIENT`, or `SKIPPED_CACHED`; failed output never replaces a valid receipt. |
| Cache key | `content_hash`, `extractor_version`, `prompt/schema_version` | Unchanged content/version is processed once; an explicit force operation is auditable. |

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| Representative jobs, GitHub, and technical-writing evidence | Produce schema-valid receipts with correct evidence/source IDs. |
| Valid span and claim output | Persist receipt and allow exact excerpt/offset resolution. |
| Unchanged evidence and extractor version | Perform zero extraction calls and return `SKIPPED_CACHED`. |
| Changed extractor version or content hash | Persist a new receipt version while retaining the prior receipt. |
| Missing field, malformed JSON, or unknown enum | Record `FAILED_VALIDATION` with actionable field errors; do not invent defaults. |
| Span outside raw evidence or mismatched excerpt | Reject the receipt and retain the validation failure. |
| Transient provider failure | Record `FAILED_TRANSIENT`, preserve pending state, and retry safely. |
| Missing raw body with snapshot reference only | Mark processing unavailable/uncertain unless an injected snapshot resolver supplies text; never load unrelated corpus data. |
| Batch limit reached | Stop at the explicit item/token/call bound and leave remaining evidence pending. |

### Authority and side-effect boundaries

This goal may read local raw evidence and call only an injected structured
extraction client; it may mutate only local receipt/attempt state. It must not
merge canonical capabilities, rank trends, construct Riffs, publish output,
execute target code, or send a full profile/corpus to a provider. Model/provider
credentials are injected and redacted. Normal tests use deterministic fakes or
recorded responses and never require paid APIs or live network access.

### Offline fixtures and state controls

Provide labeled fixtures for all three source types, valid spans/claims,
contradictory or uncertain claims, malformed/missing fields, out-of-range and
mismatched spans, transient provider failure, cached replay, extractor-version
change, missing raw body, and batch-bound exhaustion. Verify cache keys, retry
counts, duplicate calls, receipt version retention, span resolution, and stop
conditions. Keep per-item and total-call budgets explicit.

### Criterion-to-test/artifact map

| G05 criterion | Required proof artifact |
|---|---|
| Three source types | `test_receipts_cover_all_source_types` |
| Span grounding | `test_spans_resolve_to_raw_evidence` |
| Cache behavior | `test_unchanged_evidence_is_not_reprocessed` |
| Version change | `test_extractor_version_creates_new_receipt` |
| Validation/retry | `test_invalid_and_transient_outputs_are_inspectable`, `test_missing_receipt_fields_are_rejected` |
| Field-level evaluation | `test_evaluation_report_scores_each_field` |
| Raw-body boundary | `test_receipt_retrieval_does_not_load_raw_by_default` |

## Cycle verification (2026-09-14)

- `.venv/bin/python -m pytest` — **25 passed, 34 skipped** (offline suite).
- Fresh Postgres with migration `006_evidence_receipts.sql`, then
  `.venv/bin/python -m pytest -m postgres` — **34 passed**.
- `.venv/bin/python -m riff receipt evaluate --file tests/fixtures/receipts/labeled.json`
  — 3 examples; capability, technology, organization/company, claim, metadata,
  and span fields each scored separately at 1.0 accuracy.
- `git diff --check` and `.venv/bin/python -m compileall -q src tests` pass.
- Integration tests demonstrate three source types, exact span grounding,
  zero-call cache replay, extractor-version retention, inspectable validation
  and transient failures, retry behavior, and compact receipt retrieval.
