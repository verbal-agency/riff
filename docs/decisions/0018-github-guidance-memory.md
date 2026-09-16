# ADR 0018: Keep personalized GitHub guidance as a bounded projection

## Context

G34 supplies selected-repository monitoring and G26 supplies immutable,
evidence-backed project snapshots. A useful conversational answer needs to
explain what changed and suggest what to do next, but repository ownership or
activity is not evidence of personal proficiency. Conversation text also must
not silently become durable profile state.

## Decision

Additive migration 024 stores three separate projections: deterministic
snapshot deltas, versioned guidance outputs, and append-only user feedback.
Guidance is generated only from bounded project claims, cited evidence, policy
versions, and optional profile/decision/opportunity slices. It returns no more
than three actions from a fixed enum and includes uncertainty. Unchanged input
is content-addressed and idempotent; changed input creates a new version linked
to its predecessor. Feedback requires explicit confirmation at the adapter/MCP
boundary and never rewrites evidence, snapshots, or profile state.

The durable memory audit names five layers without merging their retention
rules: immutable evidence, project understanding, user decisions, guidance,
and disposable conversation context. Raw repository bodies remain outside the
guidance record by default.

## Consequences

The ChatGPT and terminal experiences can use natural project references and
show why a recommendation changed without relaying UUIDs. A human comparison
of usefulness remains an explicit evaluation rather than a protocol claim; if
it fails, the follow-up is routed to the backlog. Future ranking-policy changes
must use a new policy version so replays remain explainable.
