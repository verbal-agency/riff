# G44 — Unify evidence-backed action candidates and learn from verified outcomes

**Status:** Queued
**Depends on:** G27, G28, G29, G32, G36, G37, G39, G42, G45
**Unlocks:** Portfolio-level opportunity comparison and recommendations that improve after completed work
**Canonical scenario:** `SC-ACTION-LOOP-001`

## Outcome

Riff converts correlated signals, opportunity context, project guidance, and
prior decisions into a small number of source-agnostic, evidence-backed action
candidates. The user can compare and refine those candidates naturally, select
one through the existing approval path, and preserve the selected direction in
the resulting Exploration and PRD. After work is completed outside Riff, the
user can attach verification evidence and explicitly approve any capability or
ranking update so future recommendations reflect demonstrated results rather
than merely a completed checkbox.

This goal unifies the semantics already present in G27 recommendations, G28
`ExecutionCandidate` records, and G36/G37 guidance. It does not introduce a
second goal system or turn Riff into an execution environment.

## User-visible proof

Given several independent target-role receipts that point to durable agent
execution, a relevant Riff project seam, and no verified public capability
evidence, Riff produces one deduplicated action candidate such as:

> Extend Riff with resumable execution and idempotent tool calls. This is
> preferable to another standalone demo because Riff already contains the
> relevant multi-step workflow. Success requires a crash-recovery test showing
> that no external side effect is repeated.

The explanation identifies why the action matters now, which evidence supports
it, why it outranks the alternatives, what remains uncertain, and what would
change the recommendation. The user can ask for a greenfield comparison,
defer the action, or select it without relaying internal IDs. If selected, those
constraints and success measures survive into the approved Exploration and
later PRD. A verified result can subsequently propose a profile update or
follow-up candidate, but neither occurs without explicit user confirmation.

## Scope

### 1. Shared action-candidate projection

- Define the smallest source-agnostic projection that can represent existing
  G27 recommendations, G28 execution candidates, and G36/G37 guidance without
  replacing their authoritative records or lifecycle rules.
- Start with an adapter/read model. Add persistence only when replay,
  deduplication, selection, or provenance cannot be satisfied from existing
  immutable records; any schema change must be additive and backward compatible.
- Carry a stable candidate fingerprint, bounded action type, thesis, target
  project/goal when present, source and evidence references, rationale,
  uncertainty, effort band, expected verification evidence, policy version,
  and lineage or supersession references.
- Keep planned PRD implementation goals distinct from observed GitHub project
  goals. Document their names and relationship rather than merging them into a
  single overloaded `Goal` entity.

### 2. Correlation, deduplication, and bounded action types

- Derive candidates from combinations of Riffs, capability/profile gaps,
  opportunities, approved project maps and goals, and explicit user decisions.
- Correlate repeated evidence before candidate generation so three role receipts
  for the same capability can strengthen one candidate without creating three
  duplicate tasks or treating correlated sources as independent.
- Support only action types with defined recommendation behavior:
  `BUILD_GREENFIELD`, `EXTEND_PROJECT`, `INVESTIGATE_GAP`, `LEARN`, `PUBLISH`,
  `WAIT_FOR_EVIDENCE`, and advisory `DEPRIORITIZE`.
- Return an explicit no-action result when evidence is interesting but not
  relevant enough to an active capability, project, goal, or opportunity.
- Keep `APPLY`, `OUTREACH`, tool-executed `AUTOMATE`, and hard `STOP` semantics
  out of scope until a later goal defines their authority and downstream use.

### 3. Transparent comparison and opportunity cost

- Compare at most five candidates across opportunities or projects using
  evidence strength and independence, urgency, effort range, reversibility,
  dependency cost, project leverage, learning value, and expected competence
  evidence.
- Prefer qualitative bands, bounded estimates, and an inspectable rationale to
  unexplained decimal precision. Existing numerical scores may remain available
  for audit but cannot be the user-facing justification by themselves.
- Every ranked candidate answers: why now, why this, what evidence caused it,
  why it is preferable to the compared alternatives, and what evidence or
  condition would change the recommendation.
- Allow a well-supported `DEPRIORITIZE` or no-action result to outrank generated
  work when the portfolio already demonstrates the capability or the expected
  value does not justify the cost.

### 4. Canonical promotion through existing approvals

- Reuse the existing user-controlled Riff-to-Exploration and
  Exploration-to-PRD approval boundaries. Do not add a parallel approval or
  executable-goal lifecycle.
- Wire a selected action candidate into Exploration creation so its thesis,
  source evidence, target project/goal, constraints, alternatives considered,
  expected deliverables, and verification measures remain traceable through the
  Exploration, selected experiment, PRD, and generated goals.
- Preserve natural conversational references from G32/G37; stable IDs remain
  available in audit records but are not required in ordinary conversation.
- Rejection, deferral, correction, or supersession remains append-only and
  affects later ranking only through an inspectable policy version.

### 5. Verified outcome feedback

- Accept a bounded result record for externally completed work containing the
  selected candidate/goal, outcome, verification evidence references,
  unexpected findings, unresolved gaps, and proposed follow-ups.
- Treat goal completion as a claim, not capability proof. Verification evidence
  must be assessed through the existing evidence/profile rules before Riff can
  propose that a capability state changed.
- Require explicit user confirmation before updating profile state, suppressing
  a future recommendation as satisfied, or promoting a follow-up candidate.
- Preserve negative and partial results. A failed experiment may support an
  investigation or narrower follow-up, but it cannot silently become evidence
  of proficiency.
- Make the feedback effect inspectable: show which later candidate was removed,
  down-ranked, created, or left unchanged and which verified result caused it.

## Non-goals

- Executing generated work, modifying repositories, running coding agents,
  opening issues or pull requests, deploying systems, or operating a task queue.
- Applying for roles, sending outreach, publishing artifacts, or retiring a
  project on the user's behalf.
- Replacing the evidence ledger, signal engine, capability/profile model,
  Exploration/PRD approvals, or existing project-goal records.
- Treating a completion event, repository ownership, activity volume, or model
  prose as proof that a capability was acquired.
- Introducing another general-purpose scoring framework, opaque preference
  learning, unrestricted conversation memory, or a broad speculative action enum.

## Acceptance criteria

- [ ] Existing G27, G28, and G36/G37 outputs can be projected into one bounded
  action-candidate contract without changing or duplicating their source records.
- [ ] Three independent role receipts for one capability plus one verified gap
  produce one deduplicated candidate with all supporting evidence; correlated
  copies do not inflate confidence or create duplicate actions.
- [ ] A credible project seam produces an `EXTEND_PROJECT` candidate alongside
  a bounded greenfield alternative, while a missing seam does not force project
  reuse.
- [ ] Candidate comparison is bounded and explains why now, why this, competing
  alternatives, effort/uncertainty, and what would change the recommendation;
  it does not rely on unexplained decimal scores.
- [ ] An unrelated interesting signal yields `WAIT_FOR_EVIDENCE`, advisory
  `DEPRIORITIZE`, or an explicit no-action result rather than a manufactured goal.
- [ ] Selecting a candidate and completing the existing approvals preserves its
  evidence, target seam, constraints, deliverables, alternatives, and success
  measures in the generated Exploration and PRD.
- [ ] Rejected or deferred candidates cannot generate an Exploration, PRD, or
  profile mutation, and replay is idempotent across process restart.
- [ ] A completed goal without verification evidence does not change the
  capability profile or suppress future recommendations.
- [ ] A verified result can produce an inspectable profile-update proposal and
  alter later ranking only after explicit user confirmation; partial or failed
  outcomes retain their uncertainty and can propose bounded follow-ups.
- [ ] Offline, Postgres, adapter/MCP, and scripted conversational tests cover
  correlation, deduplication, project reuse, no-action behavior, comparison,
  natural selection, approval continuity, restart, outcome assessment, and
  confirmation boundaries.

## Deliverables

- Shared action-candidate projection and adapters over existing recommendation
  and guidance records.
- Correlation/deduplication and transparent comparison policy with versioned
  provenance.
- Candidate-to-Exploration handoff that retains the selected direction.
- Bounded verified-result record and explicit profile/ranking update proposal.
- Conversational and terminal reads for comparing candidates and inspecting why
  a verified result changed—or did not change—a later recommendation.
- Recorded fixtures and an evaluation report for the recurring-skill-gap,
  project-reuse, competing-work, no-action, and completed-result scenarios.

## Execution contract

Begin with an architecture assessment of `Recommendation`, `ExecutionCandidate`,
GitHub guidance actions, generated PRD goals, and observed GitHub project goals.
Prefer adapters and an additive projection over renaming tables or rewriting
completed services. If persistence is necessary, retain all existing IDs and
foreign-key behavior and store typed source references rather than copying raw
evidence or project bodies.

Implement in coherent slices: projection and adapters; correlation and
comparison; selected-candidate promotion; then verified-result feedback. Each
slice must preserve existing tools and approval behavior. Deterministic fixtures
must be sufficient for automated tests; no live network, paid model, external
write, or autonomous execution is required.
