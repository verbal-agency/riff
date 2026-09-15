# Decision 0012 — Versioned GitHub project maps

## Context

G26 needs a user-owned understanding of selected repositories without
conflating an existing repository with a generated Riff project or claiming
personal proficiency from repository presence.

## Decision

Store a separate `github_project_inventory` row for each explicitly onboarded
public repository, keyed by the stable G03 provider repository ID. Each refresh
creates an immutable `github_project_snapshots` version unless the bounded
inputs and parser/policy versions produce the same input hash. A snapshot's
compact claims carry evidence IDs and, when available, receipt and capability
mapping IDs. Claims are labeled `OBSERVED`, `INFERRED`, or `UNKNOWN`.

The snapshot builder reads only persisted G03 repository, README, release, and
issue evidence. It does not execute code, clone repositories, follow links, or
access private content. Repository aliases remain in the existing G03 identity
table, and archive/refresh operations are explicit user actions.

## Consequences

- G27 can consume a bounded project assessment without loading raw repository
  content or the user's full capability profile.
- Changed evidence is inspectable as a new version with a link to the prior
  snapshot; unchanged refreshes are idempotent.
- Static text matches are hypotheses only. Receipt-backed mappings retain their
  existing proposed/accepted status and do not mutate the user profile.
