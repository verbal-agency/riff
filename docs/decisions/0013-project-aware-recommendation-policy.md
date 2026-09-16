# ADR 0013: Deterministic project-aware recommendation policy

## Context

G26 gives Riff a user-approved inventory of GitHub projects and versioned
snapshots, but the signal path still treats every opportunity as greenfield.
G27 needs to recommend an existing-project extension when the evidence supports
one without turning repository metadata into an implicit capability claim or
allowing a model to choose the target.

## Decision

Persist a recommendation snapshot separately from both the GitHub project map
and the Exploration lifecycle. A deterministic matcher scores capability and
technology overlap, bounded purpose/seam text, and project health. It emits
only `EXTEND_EXISTING`, `START_NEW`, or `NOT_NOW`, with cited signal and project
evidence, uncertainty, a policy version, and a stable input fingerprint.

`EXTEND_EXISTING` is legal only with an active approved project, a current
project snapshot, an observed extension seam, and at least one cited Riff
receipt. Matching is read-only. A user confirmation plus the existing explicit
`APPROVE_EXPLORATION` decision may accept an extension and attach the stable
project ID to the Exploration; PRD generation remains a second approval.
Greenfield and defer overrides append status and reason while preserving the
original recommendation.

## Consequences

- Recommendations are reproducible and inspectable without an LLM or GitHub
  network call.
- Project metadata can guide learning value and scope without proving personal
  proficiency.
- Existing greenfield Explorations remain valid because the target reference is
  nullable and additive.
- Human evaluation is still required to judge usefulness and friction against
  the new-project-only baseline.
