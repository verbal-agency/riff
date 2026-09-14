# G13 — Operate the complete daily funnel reliably

**Status:** Queued  
**Depends on:** G09, G10, G11, G12  
**Unlocks:** G14, G15  
**PRD references:** Sections 8, 26–29, 33

## Outcome

One scheduled worker run reliably coordinates incremental collection, receipt generation, capability mapping, signal ranking, deep analysis, and daily publication with resumability, bounded model work, useful run diagnostics, and no duplicate effects.

## User-visible proof

An operator can trigger or schedule one daily run, inspect stage-by-stage counts and costs, retry a failed stage without duplicating prior work, and then query that date's zero-to-three Riffs.

## Inputs

- The completed collection, receipt, capability, profile, ranking, and Riff stage interfaces.
- Versioned pipeline policy/budget configuration and deterministic end-to-end fixtures.

## Scope

- Compose completed pipeline stages behind one run/date identity.
- Persist stage state, counts, versions, timing, failures, retry state, model-call/token/cost estimates where available, and final outcome.
- Enforce configurable funnel bounds approximating hundreds of observations, dozens of receipts, about twenty candidates, about five deep analyses, and zero to three Riffs.
- Support one-shot, resume, and safe rerun behavior with a single-worker concurrency guard.
- Add scheduling documentation/configuration for one simple scheduled process.
- Provide structured operator summaries and health/staleness information.
- Define data/version behavior when extractor, ranker, or generation policies change.

## Non-goals

- Real-time events, distributed queues, multiple workers, Kubernetes, a monitoring platform, or auto-scaling.
- Reimplementing stage logic inside the orchestrator.

## Required properties

- Durable stage completion precedes cursor/checkpoint advancement.
- A downstream failure never causes already-complete upstream work to be paid for again on normal resume.
- Concurrent runs for the same logical date/policy do not publish duplicates.
- Limits constrain expensive reasoning independently from raw collection volume.
- Partial results are visible and attributable; failure is not silently reported as “no Riffs.”

## Deliverables

- Persisted pipeline-run/stage model and orchestrator.
- One-shot/resume/rerun commands and concurrency protection.
- Funnel budget configuration and usage accounting.
- Operator status/run report and schedule/runbook documentation.
- End-to-end deterministic fixtures with injected failures at each boundary.

## Acceptance criteria

- [ ] A successful fixture run moves evidence through every stage and publishes a queryable zero-to-three daily result.
- [ ] Injected failure after any stage can resume from the last durable boundary without duplicate records or repeated completed model calls.
- [ ] Two concurrent attempts for the same run identity result in one logical publication and an inspectable loser/no-op outcome.
- [ ] Deep analysis and published-Riff caps are enforced independently of input volume.
- [ ] Run reports expose per-stage input/output/error counts, versions, durations, and model usage/cost estimates when the provider supplies them.
- [ ] A failed pipeline is distinguishable from a valid successful zero-Riff day.
- [ ] Policy-version changes create an intentional new processing/run version without corrupting earlier results.
- [ ] A documented local scheduler example invokes exactly the same tested one-shot worker path.

## Verification evidence

Run the deterministic pipeline successfully, with one injected extraction failure, with one injected deep-reasoning failure, and with concurrent duplicate attempts. Report record/model-call counts before and after resume.

## Implementation latitude

Database-backed stage state and an operating-system scheduler are sufficient. Do not add a queue or workflow engine unless a demonstrated v0.1 failure cannot be solved simply.
