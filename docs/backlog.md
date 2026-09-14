# Riff follow-up backlog

These items are routed product input from the completed G15 dogfood review.
They are not part of the v0.1 release gate and should be promoted into a new
goal only when the next development slice is selected.

## BL-G15-001 — Durable execution + observability mini-project

- **Source:** 2026-09-14 G15 user review; Riffs 1 and 2.
- **Intent:** Combine `durable-agent-execution` and `agent-observability` into
  one focused project rather than treating them as unrelated recommendations.
- **Shape:** Demonstrate resumable execution, instrument the run lifecycle, and
  evaluate whether the resulting traces make recovery and operation credible.
- **Priority:** High; this is the user's selected next investigation direction.

## BL-G15-002 — Deepen workflow reconciliation evidence

- **Source:** 2026-09-14 G15 user review; Riff 3.
- **Gap:** The current candidate has one indirect fixture receipt, no
  counterevidence, and a `KNOWLEDGE_GAP` profile state.
- **Next evidence:** Gather at least two independent direct sources, then test
  duplicate, missing, and out-of-order event cases against an explicit expected
  versus observed state invariant.
- **Decision to make:** Determine whether reconciliation is the correctness
  layer of BL-G15-001 or a separate project.
- **Priority:** High; requested before committing scope for Riff 3.

## BL-G16-001 — Persist conditional feed validators

- **Source:** G16 implementation audit.
- **Gap:** The current HTTP feed fetcher honors bounded requests and retryable
  failures, but does not persist `ETag` or `Last-Modified` validators between
  scheduled runs.
- **Why it matters:** Conditional requests would reduce bandwidth and provider
  load as the RSS inventory grows without weakening replay or provenance.
- **Destination:** Future ingestion-hardening goal; keep outside G16 because it
  changes the fetcher state contract and requires provider-response fixtures.
- **Priority:** Medium.
