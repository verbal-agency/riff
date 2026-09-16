# Decision 0017 — Origin ownership and safe retention

G35 adds additive origin metadata to persisted records. New writes may label
data as `LIVE`, `FIXTURE`, `TEST`, `QUARANTINED`, or `UNCLASSIFIED`; ambiguous
legacy rows remain `UNCLASSIFIED` and are never eligible for automatic
promotion. Fixture/test cleanup requires both an owner and origin selector,
previews the complete dependency plan, and requires an explicit `CLEANUP`
confirmation before deleting only project projections. Raw evidence, daily
Riffs, source history, and operational failures are protected.

Malformed inputs are retained in an append-only quarantine ledger with a typed
reason and provenance. Retention is versioned and dry-runnable; v0.1 records
explicit archival decisions without deleting immutable collection/evidence
history. Reports and project matching exclude non-live origins by default, with
an explicit bounded audit mode.
