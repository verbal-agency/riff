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

## BL-G31-001 — Isolate engineer-source Postgres fixtures

- **Source:** 2026-09-15 G31 operational database audit.
- **Gap:** Engineer RSS integration tests create random source rows in the
  shared development database; earlier fixture runs also lacked an explicit
  `fixture=true` marker, so aggregate coverage mixed synthetic rows with
  non-fixture-looking evidence.
- **Next step:** Run Postgres integration tests in an isolated database or clean
  test-owned rows, and require fixture metadata on every recorded fixture run.
- **Destination:** Test infrastructure/data-quality hardening before evaluating
  live engineer-source diversity.
- **Priority:** High before the live provenance acceptance gate.

## BL-G27-001 — Isolate project-recommendation fixture rows

- **Source:** 2026-09-15 G27 local dogfood run after the full Postgres suite.
- **Gap:** The recommendation tests intentionally create random project IDs in
  the shared development database, so a live `list_projects` call can show
  several synthetic projects with the same display name and affect the shape
  of a human review.
- **Next step:** Run project-map/recommendation integration tests in an isolated
  database or clean only test-owned inventory, snapshot, and recommendation
  rows before a user-facing dogfood session.
- **Destination:** Test infrastructure/data-quality hardening; no production
  matching change is required while provider IDs remain unique.
- **Priority:** High before the G27 usefulness review is finalized.

## BL-G37-001 — Human comparison of goal-aware guidance

- **Source:** G37 automated implementation; operator comparison remains
  intentionally pending.
- **Next step:** Compare one selected project goal against the G36
  profile-only baseline and record relevance, actionability, distinctiveness,
  and uncertainty honesty. Route any failed dimension to a concrete follow-up.
- **Destination:** Next connected dogfood session.
- **Priority:** Medium.

## BL-G39-001 — Human comparison of bounded riffing context

- **Source:** G39 automated implementation; operator comparison remains
  intentionally pending.
- **Next step:** In one connected session, compare the bounded goal-aware
  packet with the prior broad/profile-only context on relevance, actionability,
  distinctiveness, uncertainty honesty, and provider/fallback token usage.
- **Destination:** Next connected dogfood session; route any failed dimension
  to a concrete ranking, rendering, or budget follow-up.
- **Priority:** Medium.
