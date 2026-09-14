# ADR 0002 — Use bounded GitHub REST collection with replay-safe page cursors

**Status:** Accepted
**Date:** 2026-09-14

## Decision

G03 uses the read-only GitHub REST API for explicitly configured repositories.
The adapter collects repository metadata, releases, issues, and README
snapshots through an injected client. Responses and artifact bodies are bounded
by explicit page and byte limits. `GITHUB_TOKEN` is process-only and is never
stored in source configuration, run state, or error messages.

Each paginated endpoint has its own cursor kind. A page cursor advances only
after every artifact in that page has been durably written. A retry replays
completed pages and relies on G01's provider-ID/content-hash idempotency; this
avoids missing events when GitHub inserts a new item and shifts page boundaries.

## Consequences

- A rerun may produce duplicate retrieval outcomes while creating no duplicate
  evidence versions; this is intentional and keeps retrieval history complete.
- Repository provider IDs, fork/mirror flags, author identity, and alias
  history remain queryable for later independence reasoning.
- The initial scope does not mirror repositories, use GraphQL discussions, or
  infer trends from popularity metrics. Those can be added behind the same
  adapter contract if a later goal requires them.
