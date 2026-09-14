# ADR 0008: bounded daily Riff publication

## Context

Riff needs strong reasoning without sending the full corpus or silently
manufacturing a daily quota. Model output must remain inspectable and traceable
to the raw evidence already stored by G05.

## Decision

G09 uses an injected structured reasoning provider behind a deterministic
validation gate. Only the top configurable candidate set is assembled, with
bounded receipt/profile/decision slices. A run publishes at most three Riffs;
weak candidates, malformed output, and unknown or snapshot-only citations reduce
the count, including to zero. Date, selected inputs, and policy version form a
stable fingerprint used for idempotent reruns. The API exposes persisted results
only and never calls a model on read.

## Consequences

The deep model and prompt can change without changing the persistence contract.
Provider failures are visible as reduced output rather than fabricated balance.
Later G10 decisions can build on stable Riff IDs and the retained context,
without coupling publication to exploration or chat behavior.
