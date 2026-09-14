# G08 — Generate and rank candidate weak signals

**Status:** Queued  
**Depends on:** G06, G07  
**Unlocks:** G09  
**PRD references:** Sections 8.4, 16, 22, 24.3, 25, 28–29

## Outcome

Riff deterministically turns recent Evidence Receipts and capability mappings into an inspectable ranked set of candidate signals, materially down-weighting correlated hype, repetition, established high-volume topics, and capabilities the user already demonstrates.

## User-visible proof

An operator can inspect why a candidate ranked where it did: recency/change, independent organizations and root sources, source-type diversity, novelty, relevance, profile gap, evidence quality, and prior-decision effects are visible separately.

## Inputs

- Time-windowed receipts and normalized capability mappings from G05–G06.
- G07 profile assessments, prior decisions when present, and PRD adversarial fixtures.

## Scope

- Define candidate-signal, feature-vector, correlation-group, rank-run, and rank-explanation records.
- Generate candidates from time-windowed capability evidence rather than technology popularity alone.
- Compute deterministic features for recency/change, frequency, source-type diversity, organization/repository/author/root-source independence, capability novelty, relevance, profile state, prior decisions, repetition, and evidence quality.
- Detect or represent shared root sources and obvious corporate/repository/author correlation.
- Apply configurable, versioned ranking weights and eligibility thresholds.
- Preserve “interesting observation; insufficient evidence to call this a trend” as a possible classification.
- Add adversarial signal fixtures from PRD Section 24.3.

## Non-goals

- Deep model argument construction, publishing Riffs, autonomous online learning of weights, or optimizing to engagement.
- Treating raw evidence count, stars, or current volume as novelty.

## Required properties

- Most ranking runs without changed input/configuration are deterministic and idempotent.
- Independence and volume remain separate features.
- Normally, trend eligibility requires evidence from two source types; exceptions must be explicitly labeled as observations, not trends.
- Prior rejection changes ranking only according to the stored semantic implication and can be overcome by a material-change rule later.
- Ranking explanations expose inputs and contribution/decision logic well enough to debug.

## Deliverables

- Candidate generation, feature computation, rank configuration/versioning, and persistence.
- Correlation/root-source grouping sufficient for fixture cases.
- Rank/explanation query or report.
- Adversarial evaluation command and baseline report.

## Acceptance criteria

- [ ] Forty reposts of one announcement do not outrank a smaller cross-source, multi-root fixture solely by count.
- [ ] Twenty postings from one employer are materially down-weighted versus evidence from unrelated employers.
- [ ] High steady volume for an established technology does not create a high novelty score without meaningful recent change.
- [ ] Different frameworks implementing one underlying pattern contribute to a capability signal rather than fragmenting into unrelated skill signals.
- [ ] A capability the user already publicly demonstrates is down-ranked for personal novelty; a supported signaling gap can remain relevant with an artifact-oriented implication.
- [ ] Ten articles citing one paper retain one primary root-source group.
- [ ] A one-source-type candidate is labeled an observation/insufficient-trend-evidence unless a versioned explicit policy says otherwise.
- [ ] Re-running identical inputs and rank version yields the same ordering, explanations, and no duplicate rank records.

## Verification evidence

Produce a human-readable adversarial report showing rankings before and after independence, novelty, and profile adjustments. Include exact evidence/root/source-type counts for every fixture.

## Implementation latitude

A weighted rule-based ranker is preferred for v0.1 because it is inspectable and cheap. Statistical or learned ranking is unnecessary until product feedback produces sufficient labeled data.
