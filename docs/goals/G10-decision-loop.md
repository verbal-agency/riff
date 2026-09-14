# G10 — Add investigation, lifecycle, and semantic decision memory

**Status:** Complete
**Depends on:** G09b
**Unlocks:** G11, G14  
**PRD references:** Sections 9, 15–16, 25, 27, 33

## Outcome

The user can investigate a Riff and explicitly reject it, watch it, archive it, or approve it for Exploration. Riff stores the reasoning and ranking implications behind the decision, enforces legal lifecycle transitions, and only resurfaces rejected ideas when a material change is explainable.

## User-visible proof

After the user rejects a Riff as vendor churn around an existing capability, future ranking respects that distinction. If materially independent evidence later changes the interpretation, Riff can bring it back while stating the previous reason and what changed.

## Inputs

- Published Riffs and investigation context from G09.
- Explicit user actions and free-text reasoning supplied through the application API.

## Scope

- Define decision records with actor, Riff, decision, free-text/structured reason, semantic implications, timestamps, and policy version.
- Implement legal Riff status transitions for `NEW`, `WATCHING`, `REJECTED`, `EXPLORING`, and `ARCHIVED`.
- Require an explicit user-originated approval event for `RIFF -> EXPLORATION` eligibility.
- Support investigation operations to retrieve strongest evidence, counterevidence, capability/profile context, source/company breakdown, and raw provenance on demand.
- Translate feedback into inspectable ranking/profile implications without erasing the original words.
- Define material-change/resurfacing criteria and produce an explanation referencing prior decision and new evidence.
- Expose the small application operations needed by a future conversational adapter.

## Non-goals

- Exploration content generation, PRD creation, general-purpose conversation storage, or autonomous approval.
- Treating every conversational comment as durable preference without an explicit record action.

## Required properties

- Original decision reason is immutable; corrections append or supersede with history.
- Semantic implications distinguish novelty, relevance, capability evidence, framework aversion, and underlying-capability interest where possible.
- Rejection is not a permanent ban, but resurfacing requires a versioned material-change rule.
- The caller/actor boundary distinguishes an explicit user action from a model recommendation.
- Invalid transitions fail without partially changing decision or Riff state.

## Deliverables

- Decision and transition schema/migrations.
- Investigation, record-decision, list/history, and status-transition operations.
- Feedback-to-implication interface and deterministic test implementation.
- Material-change/resurfacing policy and explanation.
- Transition table and API documentation.

## Acceptance criteria

- [x] Rejecting a Riff stores the exact user reason plus inspectable semantic implications and changes later rank inputs accordingly.
- [x] “Too framework-specific but the underlying capability matters” penalizes framework-adoption framing without suppressing the capability itself in the corresponding fixture.
- [x] “I already understand this professionally” can create a proposed profile update and affects novelty only after the defined confirmation path.
- [x] Repeating unchanged evidence does not resurface a rejected Riff.
- [x] A material-change fixture can resurface it with a message that states the prior rejection reason and cites what changed.
- [x] Only an explicit user-originated approval can transition a Riff toward `EXPLORING`; model/system-originated attempts are rejected.
- [x] Invalid and concurrent transition attempts preserve a consistent status and complete audit history.
- [x] Investigation queries resolve evidence and counterevidence without loading unrelated corpus/profile data.

## Verification evidence

Exercise the full transition table, the PRD vendor-churn rejection, a no-change rerun, and a materially changed evidence case. Show the stored decision, resulting feature implication, and resurfacing explanation.

## Implementation latitude

Semantic implications may begin as an explicit constrained vocabulary plus structured model extraction. Preserve the raw reason so the interpretation can be improved later.

## Execution contract (satisfied in this cycle)

### Implementation surface

Added migration `011_decision_loop.sql`, `src/riff/decisions.py`, decision and
investigation endpoints in `src/riff/api.py`, and focused Postgres coverage in
`tests/test_decision_loop.py`.

### Lifecycle and decision contract

Legal transitions are `PUBLISHED|NEW -> WATCHING|REJECTED|ARCHIVED|EXPLORING`,
`WATCHING -> WATCHING|REJECTED|ARCHIVED|EXPLORING`, `EXPLORING -> ARCHIVED`,
and `REJECTED -> ARCHIVED`; rejected Riffs return to `WATCHING` only through a
material-change resurface event. `APPROVE_EXPLORATION` requires `actor_kind=USER`.
Decision reasons are immutable; corrections append with `supersedes_decision_id`.

### Criterion-to-test map

| Criterion | Proof |
|---|---|
| Reason and semantic implications | `test_rejection_stores_reason_and_framework_implications` |
| Profile confirmation path | `test_professional_knowledge_requires_confirmation` |
| No-change/material resurface | `test_unchanged_rejection_does_not_resurface_but_material_change_does` |
| Explicit user approval | `test_only_user_can_approve_exploration_and_invalid_transition_is_safe` |
| Investigation scope | `test_investigation_returns_only_linked_evidence` |
| API operations | `test_decision_and_investigation_api_operations` |

## Cycle verification

- `.venv/bin/python -m pytest -q -m 'not postgres'` — 45 passed.
- Isolated Postgres G10 integration suite — 6 passed.
- `git diff --check` passed.
