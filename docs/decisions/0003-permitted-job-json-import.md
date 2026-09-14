# ADR 0003 — Use a permitted JSON import seam for job evidence

**Status:** Accepted
**Date:** 2026-09-14

## Decision

G04 ingests jobs from a schema-versioned JSON export supplied by the operator
or a permitted provider integration. Riff does not scrape job sites or infer
missing fields. The import is bounded by an explicit content limit and uses the
G02 collection run, cursor, and item-result contracts.

Employer identity is stored separately from posting evidence. Confident
provider IDs or normalized names can correlate postings; ambiguous names create
candidate aliases and remain reversible. Exact reposts create retrieval history
without duplicate evidence versions, while changed descriptions create a new
version linked to the prior evidence.

## Consequences

- Development and evaluation are deterministic and credential-free.
- The eventual live provider can be added behind the same normalized posting
  contract after compliance and access are established.
- G15 must disclose the source/export used for dogfood evaluation; this goal
  does not claim live job-market coverage.
