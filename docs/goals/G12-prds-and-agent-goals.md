# G12 — Generate learning PRDs and executable goals

**Status:** Queued  
**Depends on:** G11  
**Unlocks:** G13, G14, G15  
**PRD references:** Sections 15, 19–20, 33

## Outcome

After the user explicitly approves a selected Exploration experiment, Riff produces a complete learning-and-building PRD and an ordered set of outcome-oriented goal documents that another capable coding agent can execute without rediscovering purpose, scope, or success criteria.

## User-visible proof

The user can review a selected experiment, approve “make it a project,” and receive a bounded PRD plus goals whose dependencies, deliverables, acceptance checks, and evidence-of-competence outcome are clear.

## Inputs

- A selected G11 experiment and a distinct user-originated PRD approval.
- Source Riff evidence, target capability/technology context, and saved Exploration decisions.

## Scope

- Define PRD/project, approval, generated-goal, dependency, version, and validation records.
- Require a distinct explicit user approval for `EXPLORATION -> PRD`.
- Generate every PRD Section 19 component: thesis, capability target, technology targets, problem/user, learning objectives, scope, non-goals, time budget, architecture, technical decisions, failure modes, acceptance criteria, evaluation plan, milestones, evidence produced, talk track, and kill criteria.
- Generate ordered implementation goals with outcome, inputs, deliverables, dependencies, acceptance criteria, non-goals, and verification evidence.
- Validate total useful slice against the 4–20 focused-hour project budget.
- Preserve key architectural/technical decisions for the user to reason about instead of deciding every implementation detail invisibly.
- Export stable Markdown and structured representations.

## Non-goals

- Running a coding agent, creating branches/PRs, guaranteeing effort estimates, or automatically publishing portfolio material.
- Generating a traditional feature PRD that omits learning and evidence outcomes.

## Required properties

- Generation cannot occur from mere selection; a separate user-originated PRD approval is mandatory.
- Generated goals state success without needlessly prescribing step-by-step implementation.
- Acceptance criteria are objective and testable where possible; subjective criteria name the human evaluator.
- Goal dependencies are acyclic and every deliverable required by a later goal has an owning earlier goal.
- The final goal proves capability gain and artifact usefulness, not just that code exists.
- Regeneration creates a new version and preserves approvals/source history.

## Deliverables

- PRD and generated-goal schema/migrations and lifecycle operations.
- Structured generation, validation, Markdown export, and versioning.
- Approval/actor guard equivalent to G10/G11.
- Validator for required sections, project budget, dependency graph, orphaned deliverables, and acceptance-criteria quality heuristics.
- Golden examples and consumer test using a clean-agent context packet.

## Acceptance criteria

- [ ] PRD generation fails without a distinct explicit user-originated approval and succeeds idempotently after approval.
- [ ] Generated PRDs contain all required Section 19 headings with nonempty, experiment-specific content.
- [ ] The useful first version is credibly bounded to 4–20 focused hours or generation returns a reduce/reframe decision.
- [ ] Generated goals form a valid directed acyclic dependency graph and collectively cover the PRD's scope, evaluation, and evidence output.
- [ ] Every goal contains outcome, inputs, deliverable, dependencies, non-goals, acceptance criteria, and verification evidence.
- [ ] Acceptance criteria reject vague completion statements such as “works well” unless paired with an explicit rubric/evaluator.
- [ ] A clean-context consumer review can state what to implement and how to prove completion using only the project PRD, one active goal, and repository state.
- [ ] Markdown export is stable, readable, and contains source Riff/Exploration/approval provenance without exposing private evidence unnecessarily.

## Verification evidence

Generate projects from at least two distinct Exploration fixtures, including a signaling-gap artifact. Run structural validation, dependency-cycle/orphan tests, budget validation, and a documented clean-context agent-readiness review.

## Implementation latitude

The consumer review may initially be a rubric-backed evaluation rather than automatic agent execution. Coding-agent execution remains explicitly outside v0.1.
