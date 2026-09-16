# Decision 0016 — Explicit GitHub watches and bounded discovery

G34 keeps user-selected repository monitoring separate from source discovery.
An active watch may collect only an already configured G03 source, using the
existing cursor/evidence transaction path. Disablement and revocation stop
network calls and cursor advancement but retain history for audit and rollback.

Quantitative search is bounded by a versioned rule: request/page and candidate
limits, independent-root and evidence thresholds, and a popularity-only guard.
Candidates retain query, policy, threshold, correlation, source, and uncertainty
provenance. Results are either queued for review or proposed in a disabled
scope; nothing becomes live collection without explicit confirmation.

The terminal one-shot path is the cron path. ChatGPT exposes compact status,
watch, search, and review operations while keeping identifiers internal to the
conversation and confirmation tokens mandatory for mutations.
