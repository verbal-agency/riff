# G29 — Calibrate confidence from provenance quality

**Status:** Complete
**Depends on:** G05, G08, G09, G22
**Unlocks:** Trustworthy high-confidence Riffs and evidence-source expansion
**PRD references:** Sections 3–6, 9, 11–15, 18–21, 27–29, 32–33
**Canonical scenario:** `SC-EPISTEMIC-001`

## Outcome

Riff distinguishes how interesting or relevant a signal appears from how well
its claim is supported. Confidence reflects provenance quality, not just a
candidate score or the strength of a generated narrative. Synthetic fixtures,
single-source assertions, syndicated copies, and incomplete citations are
visible limitations rather than silently presented as independent real-world
evidence.

## User-visible proof

When a user investigates a high-scoring Riff, Riff shows the supporting-source
count and diversity, fixture/synthetic status, root-source and organization or
author coverage, counterevidence, and any confidence limitation. For a
fixture-only signal, it explicitly says that the hypothesis may be worth
investigating but is not supported by production evidence and should not be
promoted on that basis alone.

## Scope

### 1. Provenance-quality model

- Derive a versioned quality summary from evidence receipts and their source
  metadata: real versus fixture, source type, root source, author,
  organization, publication identity, citation completeness, and counter-
  evidence coverage.
- Treat evidence independence as distinct from evidence quantity. Correlated
  roots, reposts, and multiple receipts from one organization must not create
  artificial corroboration.
- Preserve unknown values and structured reasons for missing provenance rather
  than imputing authors, companies, or production status.

### 2. Confidence and publication policy

- Separate candidate relevance/novelty score, evidence quality, and epistemic
  confidence in storage and presentation; document the relationship between
  them and keep the policy versioned.
- Define deterministic ceilings or review states for synthetic-only,
  single-source, contradictory, and otherwise insufficient evidence.
- Prevent unsupported high-confidence Riffs from being promoted to an
  Exploration or used as if they were established capability conclusions.
- Keep user decisions and later corrections auditable; recalibration must not
  erase the prior score, evidence snapshot, or decision history.

### 3. Interfaces and conversation

- Extend the read surfaces used by the API and MCP adapter to return compact
  provenance-quality summaries, confidence limitations, and promotion status.
- Keep raw evidence bounded and traceable while exposing enough provenance for
  a user to challenge a claim or request more sources.
- Preserve the existing human approval boundary; calibration explains whether
  a promotion is supported but never approves one automatically.

### 4. Evaluation

- Add deterministic fixtures for: one synthetic receipt, one real receipt,
  several independent real roots, repost-heavy volume, conflicting sources,
  and missing author or organization metadata.
- Measure unsupported-high-confidence rate, fixture-disclosure recall,
  independent-root precision, counterevidence visibility, citation coverage,
  and user correction/override behavior.
- Cover repeated runs, provenance updates, privacy redaction, bounded output,
  and backward-compatible reads in offline and Postgres tests.

## Non-goals

- Claiming that a source is real, independent, or production evidence without
  recorded provenance.
- Replacing the signal engine's ranking model or making popularity a proxy for
  truth.
- Automatically fetching arbitrary sources, enabling disabled feeds, or
  requiring a paid model or live network in tests.
- Removing fixtures; fixtures remain essential for deterministic evaluation but
  must be labelled as such in every user-facing evidence path.

## Acceptance criteria

- [x] Each investigated Riff exposes separate score, evidence-quality, and
  epistemic-confidence fields with a versioned policy identifier.
- [x] Fixture-only and single-source cases disclose their limitations and
  cannot receive an unsupported high-confidence/promotion state under the
  documented policy.
- [x] Independent roots, organizations, authors, source types, reposts, and
  counterevidence affect the quality summary without being reduced to a raw
  receipt count.
- [x] API and MCP read responses preserve compact provenance details, explicit
  unknowns, and correction history without leaking unrelated or private data.
- [x] Postgres persistence, idempotent recomputation, and prior decision
  history remain intact when provenance or policy versions change.
- [x] Offline and Postgres tests cover synthetic disclosure, independence,
  contradiction, missing metadata, privacy, bounded output, and promotion
  gating.
- [x] A human evaluation confirms that users can tell “interesting hypothesis”
  apart from “well-supported claim” and can identify what evidence is needed
  next.

## Handoff

Report the provenance-quality schema, confidence policy and ceilings, fixture
matrix and metrics, API/MCP traces, migration/backward-compatibility notes,
and the user's judgment about whether confidence now matches the evidence.
