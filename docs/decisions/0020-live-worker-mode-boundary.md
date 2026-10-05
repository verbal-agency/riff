# Decision 0020 — Explicit fixture and live worker modes

G40 makes the scheduled worker an explicit two-mode boundary. `riff worker
--fixture <path>` replays deterministic evidence and exercises the durable
seven-stage funnel without network access. `riff worker --live` composes only
enabled, reviewed database source configurations through the existing RSS,
GitHub, and permitted-job runners before running receipt extraction,
capability normalization, profile assessment, signal ranking, and bounded
daily publication.

A bare `riff worker` invocation is invalid. The worker must not report success
while doing no work, and it must never infer permission to contact a source
from the absence of a fixture. Live evidence selection is scoped to the source
IDs collected by the current run and excludes `FIXTURE`, `TEST`,
`QUARANTINED`, and `UNCLASSIFIED` origins.

The worker remains an orchestrator: source-specific parsers, cursor advancement,
retry behavior, provenance persistence, and retention rules stay in their
existing services. Provider-backed reasoning remains a separate G42 boundary;
G40 uses the deterministic provider for a live-shaped local path and honest
empty results when evidence does not produce eligible candidates.
