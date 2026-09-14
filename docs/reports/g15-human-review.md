# G15 human dogfood review

This rubric is intentionally owned by the user. Luna may report mechanical
quality and provenance, but may not infer the product-value judgment.

## Review packet

- Corpus: `tests/fixtures/dogfood/manifest.json`
- Machine report: `docs/reports/g15-dogfood-report.json`
- Daily fixture: `tests/fixtures/riffs/daily_inputs.json`
- Persisted flow covered by `tests/test_dogfood.py`: Riff, rejection/resurface,
  Exploration, selected experiment, PRD approval, PRD, and executable goals.

## Questions

1. Which Riff, if any, changed your framing of an applied-AI capability?
2. Would you choose to spend a focused session on its selected experiment?
3. Did the counterargument, evidence independence, and personalization make the
   recommendation more credible or change your conviction?
4. Final qualitative gate: did at least one Riff produce the equivalent of
   “I hadn’t framed the problem that way; I want to investigate it?” Record one
   value: `YES`, `NO`, or `UNCERTAIN`.

## Release interpretation

- `YES`: the user may authorize a v0.1 usability claim after reviewing the
  traceability report.
- `NO`: recommendation is `ITERATE`; improve signal quality before broader
  product development.
- `UNCERTAIN`: keep the recommendation `ITERATE` and run another dated corpus
  review rather than treating uncertainty as success.

## Recorded review — 2026-09-14

- Final qualitative gate: `YES`.
- Product direction: combine Riff 1 (`durable-agent-execution`) and Riff 2
  (`agent-observability`) into one mini-project. They describe complementary
  parts of one practical outcome: resumable execution with enough instrumentation
  to understand and operate it.
- Follow-up requested: provide more information on Riff 3
  (`workflow-reconciliation`) before deciding whether it belongs in that
  mini-project or deserves a separate investigation.

## Riff 3 evidence briefing

Riff 3 is a `KNOWLEDGE_GAP` candidate with `0.73` confidence and `event sourcing`
as its associated technology. Its published observation is that reconciliation
is becoming a named concern in agent systems, but the dogfood corpus currently
contains only one supporting receipt: `daily-r3`, a fixture-backed
`TECHNICAL_WRITING` record whose text says that hiring evidence names durable
execution as a requirement. That receipt is indirect evidence for reconciliation,
not a direct example of reconciliation practice. There is no counterevidence or
profile slice attached, so this is a useful hypothesis rather than a strong
trend claim.

In concrete terms, workflow reconciliation means detecting and repairing a
workflow whose expected state differs from its observed state after retries,
duplicate or out-of-order events, partial completion, or external side effects.
It is adjacent to Riff 1 (durable execution keeps work resumable) and Riff 2
(observability makes runs inspectable), but it asks a different correctness
question: can the system prove and restore the intended state?

The recommended next step is to collect at least two independent direct sources,
then run a small fixture experiment with duplicate, missing, and out-of-order
events. Define an invariant for expected versus observed state, measure whether
an event-sourced reconciliation loop repairs the discrepancy, and record repair
latency and false-repair cases. This should establish whether reconciliation is
the mini-project's core correctness layer or a separate capability worth pursuing.
