# ADR 0004 — Cache and ground Evidence Receipts

**Status:** Accepted  
**Date:** 2026-09-14

## Decision

G05 stores a compact Evidence Receipt as an immutable projection of one raw
evidence version. The cache identity is `(evidence_id, content_hash,
extractor_version)` plus the prompt/schema version recorded on each processing
attempt. A successful receipt is never overwritten; a new extractor version
creates a new receipt while retaining prior versions.

Relevant spans use offsets and an exact excerpt in the raw evidence. Validation
rejects reversed, out-of-range, mismatched, or duplicate spans, and claims may
cite only span IDs present in the validated receipt. Provider failures are
recorded as terminal attempt statuses (`FAILED_VALIDATION` or
`FAILED_TRANSIENT`) so retries are inspectable and cannot replace a valid
receipt. The provider is injected behind a small domain interface; the shipped
keyword extractor is deterministic and credential-free.

Receipt reads return only compact structured fields. Loading raw evidence is a
separate explicit repository operation.

## Consequences

- Downstream normalization can operate on bounded receipts without repeatedly
  sending full raw bodies to a model.
- Provenance remains auditable from every claim/span to one evidence version.
- Provider quality and model cost can evolve independently of the domain schema.
- Failed attempts remain available for review, while only successful receipts
  participate in cache hits.
