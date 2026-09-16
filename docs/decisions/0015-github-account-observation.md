# Decision 0015 — Explicit, public-metadata GitHub account observation

## Context

G33 needs account-aware repository selection while preserving G03's evidence
contract and G26's user-approved project inventory. Account access can expose
private repositories and credentials, so a convenient integration must not turn
ownership or activity into a capability claim.

## Decision

Use a process-only GitHub credential to fetch only the authenticated user's
bounded public repository metadata. Persist a versioned account observation,
candidate projections, and append-only status events; never persist tokens,
authorization headers, private raw responses, or repository code. Private and
inaccessible entries remain explicit omitted/unknown candidates. Selection is a
separate `PROPOSED` record and only a literal user confirmation can transition
it to `ONBOARDED` and link the selected public repository to G26.

Repeated observations are content-addressed and idempotent. Revocation and
scope narrowing block future selection while retaining historical observation
and event records for audit. G03 remains the only evidence collector; G33 may
bootstrap normalized public repository identity for a later G03 collection but
does not collect repository artifacts itself.

## Consequences

- ChatGPT and terminal flows can list and select repositories without requiring
  users to relay UUIDs; stable IDs remain available only in audit details.
- Account observation provenance cannot be confused with profile evidence,
  project snapshots, or generated Riffs.
- Live account refresh remains an explicit operator action and requires a
  reviewed credential; fixtures provide deterministic offline coverage.
