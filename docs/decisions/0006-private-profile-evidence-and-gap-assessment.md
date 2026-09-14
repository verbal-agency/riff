# ADR 0006 — Separate private profile evidence from public proof

**Status:** Accepted  
**Date:** 2026-09-14

## Decision

G07 stores profile evidence with explicit evidence level, visibility, origin,
confidence, and attestation state. Experience Ledger entries are private
`USER_ATTESTED` evidence and are excluded by public/export repository queries.
GitHub technology mentions and completed Riff artifacts enter as unknown or
candidate evidence; they do not imply hands-on proficiency.

Gap assessments are recomputable snapshots over one requested capability slice.
They retain a bounded evidence summary, rationale, uncertainty, and timestamp.
Corrections and archives append profile-history events, preserving the prior
state and provenance.

## Consequences

- Private professional experience can produce a signaling gap without being
  published or sent to unrelated model prompts.
- Sparse or conflicting evidence remains `UNKNOWN` instead of creating false
  precision.
- Profile classification can evolve after user corrections without rewriting
  source receipts or capability mappings.
