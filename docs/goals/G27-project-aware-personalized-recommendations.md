# G27 — Recommend extensions to existing projects

**Status:** Queued
**Depends on:** G08, G11, G12, G23, G24, G26
**Unlocks:** Personalized Riff-to-project dogfooding
**PRD references:** Sections 4, 6, 9, 11–15, 18–21, 27–29, 32–33
**Canonical scenario:** `SC-EXTEND-001`

## Outcome

Riff compares emerging capability signals with the user's profile and approved
GitHub project inventory, then recommends whether to extend an existing project,
start a new project, or defer the idea. An approved extension becomes an
Exploration and PRD targeted at a specific repository/project rather than an
unanchored greenfield recommendation.

## User-visible proof

When shown a Riff, the user can ask “Could this fit one of my existing
projects?” and receive a ranked set of candidate projects, the proposed seam,
expected learning value, effort and risks, cited evidence, and a clear
alternative if a new project is better.

## Scope

### 1. Matching and disposition

- Compare a candidate Riff's capability/technology requirements with project
  assessments, profile gaps, prior decisions, and project status.
- Return one or more explainable dispositions: `EXTEND_EXISTING`,
  `START_NEW`, or `NOT_NOW`, with confidence and missing evidence.
- Score fit, learning value, implementation effort, novelty, project health,
  scope risk, and evidence independence without treating popularity as fit.
- Keep deterministic eligibility and ranking separate from optional model-written
  explanations.

### 2. Targeted Exploration and PRD

- Add a durable target-project reference to the Exploration/PRD path, or an
  equivalent backward-compatible relation, while preserving existing
  greenfield projects.
- Generate extension-specific experiments, acceptance criteria, and artifacts
  that name the repository seam and distinguish learning from production scope.
- Require the same explicit user approvals for Exploration and PRD creation;
  matching never mutates a repository or creates a project automatically.

### 3. ChatGPT tools and presentation

- Add bounded adapter operations such as `list_projects`, `inspect_project`,
  `match_riff_to_projects`, and `propose_extension` to the existing tool loop.
- Return compact project summaries, cited evidence, uncertainty, and stable IDs;
  omit unrelated repository content and private profile details.
- Exercise the new operations through the G23/G24 conversational integration,
  including user correction and “start new instead” choices.

### 4. Evaluation and learning

- Create labeled fixtures where an opportunity clearly extends an existing
  project, should remain greenfield, or lacks enough evidence to decide.
- Measure disposition accuracy, recommendation usefulness, project-target
  precision, effort calibration, citation coverage, and user override rate.
- Record user feedback and decisions so later recommendations can learn from
  accepted, rejected, or deferred extension proposals.

## Non-goals

- Automatic code changes, commits, pull requests, deployments, or issue writes.
- Sending full repositories or private profile histories to a model.
- Replacing the existing signal engine, Exploration/PRD approval boundaries, or
  user authority with an autonomous planner.

## Acceptance criteria

- [ ] A candidate Riff can be matched against at least two project fixtures and
  receive an explainable extension/new/defer disposition.
- [ ] The recommendation cites project and signal evidence, shows uncertainty,
  and identifies the proposed extension seam or why none is credible.
- [ ] An explicitly approved extension creates an Exploration and PRD targeted
  at the selected existing project while preserving provenance and approvals.
- [ ] The user can override the recommendation and choose a greenfield project
  or defer it without corrupting prior state.
- [ ] ChatGPT tools expose only bounded project assessments and enforce the
  existing confirmation token and mutation boundaries.
- [ ] Offline, Postgres, and scripted conversational tests cover extension,
  greenfield, insufficient-evidence, privacy, correction, and restart cases.
- [ ] A human evaluation records whether project-aware recommendations are more
  useful and grounded than new-project-only recommendations.

## Handoff

Report the matching model and weights, disposition fixtures and metrics,
target-project persistence contract, ChatGPT tool traces, approval behavior, and
the user's qualitative judgment. Any request for automatic repository changes
must become a separately approved goal.
