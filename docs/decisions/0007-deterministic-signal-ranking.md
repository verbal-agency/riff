# ADR 0007 — Use deterministic, explainable signal ranking

**Status:** Accepted  
**Date:** 2026-09-14

## Decision

G08 ranks normalized capability candidates with a versioned weighted rule set.
The feature vector keeps raw frequency separate from source, organization,
repository, author, and root-source independence. Repeated or correlated
evidence is penalized through independence and a bounded volume adjustment;
established steady volume has zero novelty. At least two source types and two
root groups are required for trend-candidate eligibility; otherwise the result
is an explicit observation/insufficient-evidence classification.

Each rank run stores an input fingerprint, correlation groups, feature values,
weights, contributions, and eligibility rationale. Identical fingerprints reuse
the stored run.

## Consequences

- Operators can debug rankings without a model call or opaque aggregate score.
- Framework convergence and profile-state adjustments operate on capability IDs,
  not technology popularity.
- Ranking policy changes require a new config version and can be evaluated
  independently of prior runs.
