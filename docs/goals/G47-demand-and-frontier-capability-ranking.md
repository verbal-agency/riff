# G47 — Separate demand and frontier evidence in capability ranking

**Status:** Queued
**Depends on:** G08, G29, G43, G46
**Unlocks:** A defensible reading of "table stakes" versus "emerging" for G45, and ranking classes for G44
**Canonical scenario:** `SC-DEMAND-FRONTIER-001`

## Outcome

Riff ranks capabilities using two explicitly separate kinds of evidence, and
says what the relationship between them means.

- **Demand evidence** (job listings) is a lagging indicator: what employers ask
  for now. Its frequency is meaningful and already accounted for sensibly.
- **Frontier evidence** (practitioner writing, repositories, creator output) is
  a leading indicator: what capable people are building before it appears in
  listings.

Today `rank-v1` treats job listings as one source type among several inside one
blended score, so a capability that is frontier-rich and not yet in listings is
indistinguishable from one that is listing-heavy and already table stakes. This
goal makes that distinction explicit without down-weighting creators, adds
classes that describe it, and checks the underlying lead-lag hypothesis
against accumulated data instead of assuming it.

## Missing pieces this goal closes

- **Blended signal:** `source_type` only feeds a diversity count in
  `src/riff/signals.py`; nothing models demand versus frontier.
- **Neutral hard-codes:** the live worker sets per-observation `relevance=1.0`
  and `quality` to `1.0` or `0.75`, so source reputation never affects ranking.
- **Untested constants:** `profile_adjustment` values (0.25 / 0.85 / 0.65)
  dominate the score without evidence behind them.
- **Unvalidated premise:** the claim that frontier evidence precedes listings
  is central to the product and has not been measured.

## Scope

- Add a versioned classification model, `rank-v2`, as a new `rank_configs`
  version. Keep `rank-v1` runnable and its stored runs readable.
- Define two axes per capability, computed separately and never summed into
  one undifferentiated score:
  - **Demand:** listing frequency, trend over the window, employer spread, and
    repost-adjusted counts from G46 evidence.
  - **Frontier:** independent creator/repository evidence, novelty, change,
    and root/author/organization independence from non-job sources.
- Define a small, documented class vocabulary derived from the two axes, such
  as `TABLE_STAKES`, `EMERGING`, `CONVERGING`, `FADING`, `OBSERVATION`, and
  `UNCLASSIFIED`. Each class has explicit thresholds, a recorded reason, and a
  stated minimum-evidence rule. Insufficient history yields `UNCLASSIFIED` or
  `OBSERVATION`, never a confident class.
- State, in an ADR, what `source_type` means: whether it remains only a
  diversity counter or contributes typed evidence to one axis. Creators must
  not be diminished merely because their volume is lower than listings.
- Replace the hard-coded `quality` and `relevance` observation values with
  either a documented derivation or an explicit, recorded neutral policy. Do
  not introduce unreviewed per-source reputation weights.
- Test the `profile_adjustment` constants against fixtures and either justify,
  replace, or make them configuration with recorded rationale.
- Preserve G29 provenance ceilings: a class can never raise confidence above
  the ceiling its evidence supports.
- Add a lead-lag evaluation harness over accumulated history. For capabilities
  with enough data, measure whether frontier evidence preceded demand growth,
  by how long, and how often it did not. Report the result with its sample size
  and uncertainty.
- Make the class and both axes inspectable on existing read surfaces, with
  plain-language explanations that cite supporting receipts. Do not require
  users to read internal feature names.
- Run `rank-v1` and `rank-v2` over the same evidence and record a comparison
  for G45 to consume.

## Non-goals

- Manually assigning per-source-type or per-creator weights, or ranking by
  popularity, follower counts, or star counts.
- Predicting listings with a model, or presenting the lead-lag finding as a
  forecast. It is an evaluated hypothesis with stated limits.
- Changing which sources are collected (G46) or how evidence is extracted
  (G43).
- Redesigning recommendation selection (G44) beyond exposing the new classes.
- Removing or rewriting `rank-v1` history.

## Acceptance criteria

- [ ] `rank-v2` is stored as a new versioned configuration; existing
  `rank-v1` runs remain readable and re-runnable and are not mutated.
- [ ] Every ranked capability exposes separate demand and frontier values, its
  class, the class thresholds applied, and the reason, without collapsing the
  axes into one number before classification.
- [ ] Fixtures demonstrate each class: a frontier-rich, listing-poor capability
  is `EMERGING`; a listing-heavy, frontier-flat one is `TABLE_STAKES`; sparse
  or single-source evidence is not given a confident class.
- [ ] Insufficient history (fewer than the configured weeks of job evidence)
  yields an explicit `UNCLASSIFIED` or `OBSERVATION` result with the reason,
  not a guessed class.
- [ ] A class never increases epistemic confidence above the G29 provenance
  ceiling for the supporting evidence.
- [ ] Lower-volume creator evidence is not penalized for volume alone; a test
  shows the same frontier evidence yields the same frontier value regardless of
  how many listings exist.
- [ ] The previously hard-coded `quality`, `relevance`, and
  `profile_adjustment` values are each documented, justified by evidence, or
  made configurable with a recorded rationale.
- [ ] The lead-lag harness runs deterministically on a recorded fixture history
  and on accumulated live history, and reports lead time, sample size, and
  cases where the frontier did not precede demand. A result that does not
  support the hypothesis is recorded as such.
- [ ] A `rank-v1` versus `rank-v2` comparison on identical evidence is recorded
  for G45, with differences explained.
- [ ] Automated tests make no live network or paid-provider calls. Whether the
  classes feel useful is explicitly marked as owner judgment for G45.

## Deliverables

- ADR defining the two axes, the class vocabulary and thresholds, the role of
  `source_type`, and the cold-start rule.
- `rank-v2` implementation and migration for any additive state.
- Lead-lag evaluation harness and a recorded evaluation report.
- Updated read-surface projections and plain-language explanations.
- `rank-v1` versus `rank-v2` comparison record.
- Focused fixtures and tests.

## Execution contract

### 1. Write the ADR before the code

The axes, classes, and the meaning of `source_type` are consequential and
contested. Record them first, including the alternatives considered (a single
blended score with source-class weights; source-class reputation priors) and
why they were rejected.

### 2. Classify, do not blend

Compute demand and frontier independently, then classify from thresholds.
A blended number may be retained for ordering within a class, but it must not
replace the classes or hide which axis drove the result.

### 3. Be honest about cold start

Lead-lag requires weeks of job history from G46. Until enough exists, the
system must say so and avoid confident class labels. Do not backfill or
simulate history to make early runs look decisive.

### 4. Protect independence and provenance

Reuse the existing independence features and G29 ceilings. A class is a
description of evidence shape, not a promotion of confidence. Reposts and
duplicate content continue to be discounted before either axis is computed.

### 5. Keep it replayable

Ranking must be reproducible from stored evidence under a named configuration,
with the same fingerprint behavior as `rank-v1`, so G45 can compare versions on
identical inputs and later changes remain reversible.

### 6. Verify and report

Run focused tests, then the lead-lag harness on whatever real history exists.
State which acceptance criteria are automated, which depend on accumulated
history, and which are owner judgment deferred to G45.
