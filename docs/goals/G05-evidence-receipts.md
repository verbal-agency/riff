# G05 — Produce compact, versioned Evidence Receipts

**Status:** Queued  
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

- [ ] Representative items from all three source types produce schema-valid receipts with correct evidence IDs and source metadata.
- [ ] Every extracted relevant span resolves to a valid location or exact excerpt in the stored raw evidence.
- [ ] A second run over unchanged evidence and extractor version performs zero extraction calls.
- [ ] Changing the extractor version produces a new receipt version while retaining the prior one.
- [ ] Malformed, missing-field, out-of-source-span, and transient-provider responses have tested, inspectable outcomes and safe retry behavior.
- [ ] The evaluation report scores capability, technology, organization/company, claim, metadata, and span extraction separately.
- [ ] Downstream receipt retrieval does not require loading the raw body unless explicitly requested.

## Verification evidence

Run the labeled fixture evaluation with a deterministic extractor and, if configured, an optional live extractor. Record cache call counts across unchanged and version-changed reruns, plus validation failures for an intentionally hallucinated span.

## Implementation latitude

Exact quality thresholds should be baselined here rather than invented without data. The report must expose per-field errors so later work can set justified gates. Avoid optimizing a single aggregate score that hides provenance failures.
