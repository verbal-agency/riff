# G11 — Turn approved Riffs into bounded Explorations

**Status:** Complete
**Depends on:** G10  
**Unlocks:** G12  
**PRD references:** Sections 12, 15, 17–18, 33

## Outcome

After explicit user approval, Riff can create and collaboratively refine an Exploration that preserves the Riff thesis, identifies open questions, and offers several capability-driven experiments with at least one valuable 4–20 focused-hour vertical slice.

## User-visible proof

The user can approve a Riff, compare meaningfully different build/measurement experiments, reject boring options, revise the promising one, and save an Exploration without a PRD being generated prematurely.

## Inputs

- A G10 Riff with an explicit user-originated Exploration approval.
- Its capability/profile context, evidence-backed thesis, and user refinement feedback.

## Scope

- Define the PRD Exploration fields, status, version/history, and relationship to one source Riff.
- Enforce the explicit approval recorded by G10 before creation.
- Generate thesis, why it matters, learning question, capability and technology targets, open questions, possible experiments, estimated effort, and competence evidence.
- For each experiment, cover the learning pipeline: understand, implement, inspect, compare, demonstrate.
- Evaluate project-selection rules: useful, capability-driven, concrete, discussable, completable, and portfolio-capable when possible.
- Support user edits, option rejection, regeneration with constraints, and explicit experiment selection.
- Keep Exploration deliberation distinct from PRD approval.

## Non-goals

- Automatic promotion, PRD generation, coding-agent execution, curricula, or ideas estimated above 20 hours without reducing them.

## Required properties

- No Exploration exists without a traceable user approval and source Riff.
- Experiments develop/demonstrate the underlying capability, not just wrapper familiarity with a named framework.
- Technology fluency remains concrete: at least one representative implementation is inspected or used where relevant.
- Effort estimates state assumptions and uncertainty.
- User edits and rejected options remain in versioned decision history so they inform refinement.

## Deliverables

- Exploration schema/migrations and lifecycle operations.
- Structured generation/refinement boundary with validation.
- Experiment scoring against project-selection rules.
- Versioned edit/select behavior and presentation DTO.
- Golden fixtures for valid exploration, no approval, overlarge project reduction, signaling-gap artifact, and user refinement.

## Acceptance criteria

- [x] Creation fails without an explicit G10 user-approval record and succeeds idempotently with one.
- [x] A generated Exploration includes every PRD schema field and multiple materially different experiment options.
- [x] At least one option has a credible 4–20 focused-hour useful slice with assumptions and a concrete artifact or measurement.
- [x] Every option maps its work and evidence of competence to the target capability and names representative technology fluency where relevant.
- [x] A project above the time budget is reduced to a valuable slice or rejected rather than mislabeled as completable.
- [x] A signaling-gap fixture favors a public demonstrative artifact over redundant study.
- [x] User rejection/refinement changes later options while preserving the original option and semantic reason.
- [x] Selecting an experiment does not itself create a PRD or imply PRD approval.

## Verification evidence

`tests/test_explorations.py` provides deterministic schema, signaling-gap, overlarge-reduction, approval-boundary, idempotence, refinement-history, selection, and API coverage. Offline verification: `.venv/bin/python -m pytest -q -m 'not postgres'` (47 passed). PostgreSQL integration verification: `.venv/bin/python -m pytest -q -m postgres tests/test_explorations.py` (3 passed).

## Implementation contract delivered

- `src/riff/migrations/012_explorations.sql` stores one Exploration per approved Riff, relational experiments, append-only versions, and lifecycle events.
- `src/riff/explorations.py` is the deterministic generator/repository boundary. It requires a user `APPROVE_EXPLORATION`, validates the PRD fields and 4–20 hour rules, supports semantic refinement/rejection, and selects an experiment without creating a PRD.
- API operations are `POST /riffs/{riff_id}/explorations`, `GET /explorations/{exploration_id}`, `POST /explorations/{exploration_id}/refine`, and `POST /explorations/{exploration_id}/select`.
- G12 owns PRD approval and generation; this goal intentionally stops at a selected Exploration experiment.

## Implementation latitude

The number of experiment options is not fixed; aim for enough real choice without filler. Quality is more important than producing a quota of alternatives.
