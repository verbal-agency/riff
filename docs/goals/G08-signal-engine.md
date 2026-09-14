# G08 — Generate and rank candidate weak signals

**Status:** Ready
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

## Execution contract for the next Luna run

### Expected implementation surface

Extend `src/riff` with candidate-signal, feature-vector, correlation-group,
rank-run, and rank-explanation records plus deterministic generation and
ranking services over G05 receipts, G06 mappings, and G07 assessments. Add the
next numbered migration, focused tests in `tests/test_signal_engine.py`,
adversarial fixtures under `tests/fixtures/signals/`, and a human-readable
evaluation command/report. Document operator inspection in `README.md` and
`docs/architecture.md`; add an ADR for ranking weights or correlation policy.

### Canonical domain and persistence contract

| Concept | Required fields | Invariants |
|---|---|---|
| Candidate signal | `signal_id`, `capability_id`, `classification`, `window_start`, `window_end`, `rank_run_id` | Candidate is capability-based; `OBSERVATION` is valid when trend evidence is insufficient. |
| Feature vector | recency/change, frequency, source-type diversity, organization/repository/author/root independence, novelty, relevance, profile state, repetition, quality | Independence and volume remain separate numeric features with inspectable inputs. |
| Correlation group | `group_id`, `root_source`, member evidence IDs | Shared roots, organizations, repositories, and authors are represented without deleting evidence. |
| Rank run | `rank_run_id`, `config_version`, `input_fingerprint`, `created_at` | Same inputs and config produce one deterministic ordering and no duplicate run. |
| Explanation | feature values, weights, contributions, eligibility decision | Every score and trend/observation decision is auditable from bounded evidence. |

Use explicit classification values `TREND_CANDIDATE`, `OBSERVATION`, and
`INSUFFICIENT_TREND_EVIDENCE`; persist versioned weights and eligibility policy.

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| Forty reposts of one announcement | Do not outrank a smaller cross-source, multi-root signal solely by count. |
| Twenty postings from one employer | Employer-correlated volume is materially down-weighted. |
| High steady volume without recent change | No high novelty score or trend eligibility. |
| Multiple frameworks for one capability | Contribute to one capability signal, not separate framework skills. |
| Publicly demonstrated capability | Personal novelty is down-ranked; a supported signaling gap may remain relevant with artifact implication. |
| Ten articles citing one paper | One primary root-source group is retained. |
| One source type | Label observation/insufficient evidence unless an explicit policy exception applies. |
| Identical rerun | Same order, explanations, and persisted rank identity; no duplicates. |

### Authority and side-effect boundaries

Read only local receipts, mappings, profile assessments, and prior decisions;
mutate rank-run, correlation, candidate, and explanation state. Do not publish
Riffs, alter profile evidence, rewrite receipts, call paid providers, or infer
trend labels from stars/counts alone. Model assistance is out of scope unless
behind an injected, bounded interface; normal tests use deterministic fixtures.

### Offline fixtures and state controls

Provide repost burst, single-employer burst, steady established volume,
framework fragmentation, public-demonstrated, signaling-gap, shared-root,
one-source-type, prior-rejection, duplicate-rerun, malformed-input, and
budget-exhaustion fixtures. Verify input fingerprints, correlation groups,
feature contributions, eligibility labels, rank ordering, replay idempotence,
and explicit item/call limits.

### Criterion-to-test/artifact map

| G08 criterion | Required proof artifact |
|---|---|
| Repost independence | `test_reposts_do_not_win_by_count` |
| Employer correlation | `test_single_employer_burst_is_downweighted` |
| Steady volume novelty | `test_steady_volume_is_not_novel` |
| Framework convergence | `test_frameworks_share_capability_signal` |
| Profile adjustment | `test_profile_state_changes_personal_novelty` |
| Shared roots | `test_shared_root_articles_form_one_group` |
| Source-type policy | `test_one_source_type_is_observation` |
| Deterministic rerun | `test_identical_rank_run_is_idempotent` |
