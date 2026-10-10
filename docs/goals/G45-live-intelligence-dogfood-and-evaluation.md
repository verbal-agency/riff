# G45 — Dogfood live intelligence and establish a usefulness gate

**Status:** Queued
**Depends on:** G29, G32, G39, G41, G42, G43
**Unlocks:** G44 and expansion of unattended live operation
**Canonical scenario:** `SC-LIVE-DOGFOOD-001`

## Outcome

Before Riff expands its action-candidate and outcome-feedback model, its owner
can use a live, connected Riff repeatedly to investigate current signals and
receive grounded, intelligible recommendations. The system either produces a
useful result with inspectable evidence or explains precisely why it cannot;
an empty, partial, stale, fixture-only, or low-evidence run is never presented
as a successful intelligence result.

This is a dogfood and evaluation gate, not a claim that every scheduled run
will produce a novel recommendation. The point is to establish whether the
smallest complete live loop is worth iterating on.

## Missing pieces this goal closes

- **Operational trust:** G41 must make an invocation's readiness, lease state,
  source coverage, failure class, and remediation visible to the operator.
- **Live evidence yield:** G43 has the extraction/replay mechanics, but live
  collection still needs to be judged on current source availability,
  diversity, and whether the retained receipts clear the publication bar.
- **Grounded synthesis:** G42 must turn a bounded live evidence packet into a
  provenance-linked result without replacing an honest empty or weak-evidence
  outcome with plausible prose.
- **Conversation quality:** G32/G39 must let the owner explore a result,
  reject it, request an alternative, compare it to a project or scenario, and
  see the supporting evidence without UUIDs, raw prompt dumps, or an
  unbounded context payload.
- **Evaluation evidence:** Riff currently has architecture and controlled
  slices, not proof of recurring real-world usefulness. A recorded owner
  evaluation is required before later recommendation-learning work treats the
  product loop as established.

## Scope

- Define a small, repeatable dogfood protocol covering readiness, one live
  collection run, a live-evidence replay when needed, daily-result inspection,
  and natural connected follow-ups.
- Run the protocol over several explicitly recorded windows or source states:
  a useful published result when the evidence supports one, a valid empty or
  insufficient-evidence result, and a partial/source-failure result. Recorded
  fixtures may reproduce adverse states, but cannot stand in for the live
  useful-result check.
- Assess each result for provenance completeness, source diversity,
  confidence calibration, recommendation specificity, conversational
  usefulness, and operator clarity. Record the owner’s judgment separately
  from automated checks.
- Classify every failure as one of: source availability/permissions, source
  quality or diversity, extraction/normalization, correlation/ranking,
  provider grounding, context/retrieval, interaction design, or operator
  ergonomics. Attach concrete evidence and a bounded remediation.
- Fix only blockers that prevent the protocol from reaching a trustworthy
  result. Route non-blocking discoveries into separately scoped goals; do not
  absorb G44 or expand the product during dogfooding.
- Publish a redacted operator runbook with one-line local commands and a
  concise interpretation guide for success, empty, partial, stale recovery,
  and readiness failure.

## Non-goals

- Guaranteeing a daily Riff, lowering evidence thresholds to manufacture one,
  or treating model fluency as useful intelligence.
- Automating applications, outreach, repository changes, or execution of a
  candidate recommendation.
- Expanding to an unrestricted corpus, adding a general analytics dashboard,
  or requiring an always-on hosted deployment.
- Treating a single favorable conversation or a fixture replay as proof that
  Riff is a dependable ongoing recommendation product.

## Acceptance criteria

- [ ] The documented protocol can be run locally end-to-end without internal
  IDs or ad hoc environment debugging, and every command has an interpretable
  result and recovery path.
- [ ] At least one connected live-evidence run is assessed end-to-end: its
  published Riff or honest non-publication has traceable receipts, source and
  origin information, calibrated confidence, and a canonical G41 report.
- [ ] The protocol records and clearly distinguishes a valid empty or
  insufficient-evidence result from partial collection, readiness failure,
  fixture-only replay, and provider failure; none is called a successful
  recommendation.
- [ ] In a connected conversational session, the owner can ask naturally why
  a recommendation matters, inspect its evidence/uncertainty, request an
  alternative, and map a candidate to a chosen project or scenario without
  relaying UUIDs.
- [ ] At least three owner-evaluated sessions or windows are recorded, with
  source coverage and outcome class. The evaluation reports what was useful,
  what was not, and whether Riff should advance to G44.
- [ ] Every material defect found has an RCA and is either fixed within this
  goal because it blocks trust, or routed to a specific future goal with a
  narrow outcome and dependency.
- [ ] Automated regression checks cover the protocol's deterministic portions;
  the human usefulness judgment is explicitly marked as human evidence rather
  than inferred from passing tests.

## Deliverables

- Versioned dogfood protocol and redacted operator runbook.
- Recorded live and adverse-outcome evaluation artifacts, including canonical
  reports and provenance summaries.
- Owner evaluation template and a concise findings/RCA record.
- Only the focused fixes necessary to complete the trustworthy live loop, plus
  follow-up goals for all remaining material gaps.

## Execution contract

Begin only after G41, G42, and G43 have their stated automated acceptance
evidence. Use G41's canonical reports and readiness command, G43's origin-safe
replay, G42's bounded provider records, and G32's natural-language handles;
do not create parallel health, replay, or conversational state.

The first step is an evidence-led baseline, not an implementation spree:
capture current source readiness and the bounded results of the protocol. A
missing live result is a valid finding. For each blocker, show the source/run
report, expected behavior, actual behavior, classification, and proposed
remediation. Only then implement a narrowly necessary correction. The final
owner decision is explicit: **advance to G44**, **iterate on named blockers**,
or **pause live expansion**.
