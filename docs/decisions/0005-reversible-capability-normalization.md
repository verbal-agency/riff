# ADR 0005 — Keep capability normalization reversible

**Status:** Accepted  
**Date:** 2026-09-14

## Decision

G06 stores capabilities and technologies in separate tables and connects them
through many-to-many relationships. Every receipt candidate creates an
immutable provenance-bearing mapping with confidence, rationale, entity type,
and explicit status. Deterministic aliases may resolve synonymous phrases to a
transferable capability, but technology names never become capability names by
default.

Review operations append `normalization_decisions`. Accept, reject, remap, and
split update the current mapping state while preserving its receipt and
candidate text; undo restores the prior state from the decision history. A
normalizer version is part of mapping identity so reruns are idempotent and
version changes can be evaluated independently.

## Consequences

- Distinct concepts such as agent memory and workflow persistence remain
  separate unless a reviewer explicitly relates them.
- Framework fragmentation strengthens a shared capability instead of creating
  product-named capability nodes.
- The graph is inspectable in both technology-to-capability directions and can
  be corrected without mutating source evidence.
