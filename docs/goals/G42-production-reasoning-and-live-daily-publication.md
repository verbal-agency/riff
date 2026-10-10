# G42 — Wire a replaceable reasoning provider into live daily publication

**Status:** Queued
**Depends on:** G40, G41, G39, G29, G23, G24a
**Unlocks:** End-to-end live Riff dogfooding
**Canonical scenario:** `SC-LIVE-RIFF-001`

## Outcome

Riff can take a live, provenance-qualified daily evidence set through bounded
reasoning and publish a grounded daily Riff, while remaining provider-neutral.
The model sees compact receipts and relevant profile/project/opportunity slices,
not raw unrestricted source bodies or an unbounded conversation history.

## Scope

- Connect the existing replaceable `ReasoningProvider` seam to the live daily
  pipeline with explicit provider/model configuration and a deterministic
  offline fake for tests.
- Reuse G39 context packets and G29 provenance-quality ceilings when building
  candidate prompts/inputs; preserve citations, counterevidence, uncertainty,
  and source diversity in the generated result.
- Enforce per-run candidate, call, token, time, and cost budgets. Cache or
  fingerprint completed calls so retries do not repeat paid work.
- Record provider usage estimates/telemetry without persisting raw prompts or
  unrestricted model responses.
- Consume G41's canonical worker report, readiness result, lease, and exit-code
  contract. Provider work starts only after the run is ready, and provider
  telemetry augments that report rather than creating parallel health state.
- Treat provider timeout, invalid output, budget exhaustion, and insufficient
  evidence as explicit non-publication or valid-empty outcomes.
- Provide one recorded provider-response end-to-end test and one explicitly
  authorized operator smoke run against the connected ChatGPT/provider path.

## Non-goals

- Hard-coding OpenAI/ChatGPT as the only provider, training a model, or sending
  the full evidence corpus/profile to a model.
- Allowing model output to approve Explorations, PRDs, source enablement, or
  other user-authority mutations.
- Claiming live usefulness from protocol success alone; human evaluation remains
  a separate acceptance step.

## Acceptance criteria

- [ ] A live-shaped run with a recorded provider response produces a persisted,
  provenance-linked Riff or an explicit valid-empty result.
- [ ] Provider selection, model version, context-policy version, input
  fingerprint, usage, and cost estimate are visible in the run report.
- [ ] Fixture/test evidence cannot raise live confidence or appear as live
  support without an explicit audit/include mode.
- [ ] Invalid, unsupported, over-budget, timed-out, or insufficient-evidence
  provider results never publish an ungrounded Riff.
- [ ] Repeating an identical run reuses durable results and does not repeat
  completed paid provider calls.
- [ ] A provider timeout or invalid output is represented through G41's durable
  run/stage and outcome contract; it cannot bypass an active lease or be hidden
  by a successful terminal exit code.
- [ ] Offline, Postgres, connector, and one connected human acceptance check
  cover grounding, uncertainty disclosure, redaction, and budget behavior.

## Deliverables

- Provider configuration and live-pipeline adapter implementation.
- Context/rendering and usage telemetry integration.
- Recorded provider fixtures, failure fixtures, and Postgres assertions.
- Updated operator documentation for local, connected, and cron execution.

## Execution contract

G42 extends the completed G41 run rather than wrapping it. It may add provider
usage, cache, and reasoning-result fields to the canonical run report, but it
must preserve G41's lease ownership, append-only recovery history, source
readiness classification, and terminal exit-code behavior. Provider retries are
stage-bound and fingerprinted; an active or non-stale run is never reclaimed to
repeat a paid call.
