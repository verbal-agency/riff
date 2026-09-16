# ADR 0014 — Opportunity context and execution riffing policy

## Decision

Riff stores opportunity constraints separately from capability conclusions and
generates a bounded family of execution candidates before any Exploration or
PRD approval. Named platforms, including Perplexity Computer, are recorded as
opportunity context and constraints; they are not universal implementation
choices. Project-aware candidates require an explicit credible seam, otherwise
the greenfield alternative remains valid.

Candidate transformations (`COMBINE`, `EXTEND`, `NARROW`, `INVERT`, `TRANSFER`,
and `CONSTRAIN`) create immutable parent-linked variants with deterministic
IDs, input hashes, scores, assumptions, and rationale. Selection records the
user's direction but does not create an Exploration or PRD.

## Rationale

The target opportunity should constrain the search without overfitting the
product to one job or platform. Persisted context and lineage make it possible
to compare distinctive demonstrations, preserve uncertainty, and explain why
an existing project is or is not worth extending.

## Boundaries

Fixture extraction is offline and secret-free. Live URL fetching remains in the
existing permitted job-ingestion boundary. Candidate generation and riffing do
not call models, access repositories, or mutate upstream systems. Only the
later Exploration/PRD approval boundaries can authorize project generation.
