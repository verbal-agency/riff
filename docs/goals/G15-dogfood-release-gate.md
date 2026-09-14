# G15 — Pass the Riff v0.1 dogfood release gate

**Status:** Complete
**Depends on:** G00–G14  
**Unlocks:** Riff v0.1 usability claim  
**PRD references:** Sections 5, 24, 30–35

## Outcome

Riff is evaluated end to end on its own applied-AI problem space using representative historical evidence, all PRD v0.1 acceptance criteria have traceable evidence, and the user makes the qualitative go/no-go judgment based on whether at least one Riff reveals a valuable framing they would not otherwise have pursued.

## User-visible proof

The system consumes several weeks of job, GitHub, and curated technical-writing evidence, produces up to three emerging applied-AI capability arguments, supports real deliberation, and turns one user-approved idea into an Exploration and completable PRD with agent-ready goals.

## Inputs

- The complete G00–G14 system with fixed release-candidate policy versions.
- A dated multi-week corpus, automated evaluation fixtures, and the user's qualitative review.

## Scope

- Assemble a reproducible, dated dogfood corpus spanning all three primary source categories and several weeks where source terms permit storage/replay.
- Complete the extraction, normalization, adversarial signal, product, privacy, approval, and end-to-end evaluation suite.
- Run the daily pipeline on the corpus with production-equivalent policies and capture funnel/cost/quality diagnostics.
- Review resulting Riffs against novelty, relevance, conviction change, evidence independence, argument quality, and counterfactual value rubrics.
- Exercise rejection memory and both explicit promotion boundaries.
- Convert one user-approved Riff through Exploration to a 4–20-hour project PRD and executable goals.
- Produce a PRD Section 33 traceability report and honest release recommendation.

## Non-goals

- Adjusting fixtures or thresholds solely to force three Riffs, declaring success from synthetic tests alone, automatically claiming the user's “aha,” or implementing the generated dogfood project.
- Expanding to multiple users or out-of-scope v0.1 features.

## Required properties

- Corpus provenance, capture dates, permitted storage mode, and fixture limitations are documented.
- Evaluation separates mechanical correctness from subjective product value.
- A successful zero-Riff run is allowed, but it does not satisfy the first-dogfood qualitative criterion.
- Failures and uncertainty remain visible in the report.
- The user—not Luna—owns the final novelty/value judgment and any decision to continue broader development.

## Deliverables

- Reproducible dogfood corpus manifest or import recipe.
- Consolidated automated evaluation command and machine/human-readable reports.
- Daily funnel run report with selected candidates and published results.
- Human review rubric and recorded user decisions.
- One approved Exploration and generated PRD/goals if the user chooses a Riff.
- Acceptance traceability matrix covering every PRD Section 33 criterion.
- Release recommendation: pass, iterate signal pipeline, or stop/reframe.

## Acceptance criteria

- [x] The corpus includes several weeks of representative jobs, GitHub activity, and curated technical writing with resolvable provenance.
- [x] Extraction and capability-normalization reports expose errors and show no release-blocking provenance failure or systematic over-merging under the documented rubric.
- [x] Every PRD Section 24.3 adversarial fixture passes its explicit ranking expectation.
- [x] A production-equivalent run publishes zero to three Riffs, and every published claim passes provenance, independence, counterargument, and personalization review.
- [x] Rejection reason affects a later run, unchanged rejection is not resurfaced, and a material-change case explains why it returns.
- [x] System enforcement prevents unapproved Riff -> Exploration and Exploration -> PRD transitions in end-to-end tests.
- [x] If the user approves a result, it reaches a bounded Exploration and PRD whose goals pass the G12 agent-readiness validator.
- [x] The Section 33 traceability matrix links every acceptance criterion to a test, report, demonstration, or named human review result.
- [x] The user records whether at least one Riff caused the equivalent of “I hadn't framed the problem that way; I want to investigate it.” This criterion cannot be self-certified by Luna. Recorded as `YES`; the user wants Riffs 1 and 2 combined into one mini-project.
- [x] If the prior criterion fails, the release recommendation is to improve the signal pipeline before broader product development, as required by the PRD. N/A because the prior criterion passed; the recorded recommendation is `PASS`, with Riff 3 follow-up routed to the backlog.

## Verification evidence

Archive the exact corpus manifest, configuration/policy versions, commands, funnel report, generated Riffs, user rubric responses, transition audit, Exploration/PRD exports, and traceability matrix. Redact private experience descriptions while retaining proof that privacy and personalization checks ran. Current machine report: `docs/reports/g15-dogfood-report.json`; user rubric: `docs/reports/g15-human-review.md`. Automated verification: 51 offline tests, 83 PostgreSQL tests, and the focused dogfood integration test passes. The user recorded `YES`; Riffs 1 and 2 are one mini-project, and Riff 3 has a documented evidence-gap follow-up.

## Execution contract

Expected implementation surface: a versioned corpus manifest/import recipe under
`tests/fixtures/dogfood/` or `config/`, evaluation/report modules under
`src/riff/`, focused tests in `tests/test_dogfood.py`, and release artifacts in
`docs/reports/` plus this goal file. Reuse the G05–G14 stage and approval APIs;
do not fork domain logic into the report generator.

Canonical artifacts are immutable-by-reference: corpus manifest with capture
dates/terms/storage mode, policy-version manifest, funnel report, generated
Riff/decision/transition records, Exploration/PRD/goal exports, human rubric,
and Section 33 traceability matrix. Reports must distinguish `PASS`, `ITERATE`,
and `STOP` recommendations and preserve uncertainty/redaction notes.

Behavior matrix:

| Condition | Required result |
|---|---|
| Complete permitted corpus | Production-equivalent funnel report and zero–three persisted Riffs |
| Missing/expired terms or provenance | Import/evaluation failure with the affected source named; no silent inclusion |
| Adversarial fixture expectation fails | Mechanical evaluation failure recorded; release cannot pass by aggregate score |
| User rejects a Riff | Later unchanged run does not resurface it; material evidence change explains return |
| No user approval | Exploration/PRD transition is rejected and traceable |
| User approves both boundaries | One provenance-linked Exploration, selected experiment, PRD, and agent-ready goals |
| User does not confirm the qualitative “aha” | Recommendation is `ITERATE` or `STOP`, never self-certified pass |

Authority and side effects: collection must honor each manifest's storage and
terms decision; private profile text is redacted from exported artifacts;
network/live sources are disabled unless the manifest explicitly permits them;
the user's qualitative judgment is required and cannot be inferred by Luna.
Evaluation fixtures are deterministic and offline where possible, and reports
must include command, policy, input fingerprint, and artifact IDs for replay.

Criterion map: `test_corpus_manifest_provenance`,
`test_adversarial_expectations`, `test_production_funnel_report`,
`test_rejection_memory_and_resurface`, `test_approval_boundaries`,
`test_delivery_traceability`, and `test_human_release_decision_required` map
to the acceptance criteria above. Include positive, malformed, contradictory,
private-redaction, missing-approval, zero-Riff, and partial-failure fixtures.

## Implementation latitude

Automated quality thresholds should be based on baselines established in earlier goals and documented here. No aggregate score may override a provenance breach, human-approval breach, or the user's qualitative dogfood judgment.
