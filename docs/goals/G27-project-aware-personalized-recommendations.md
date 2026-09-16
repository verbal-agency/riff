# G27 — Recommend extensions to existing projects

**Status:** Complete
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

- [x] A candidate Riff can be matched against at least two project fixtures and
  receive an explainable extension/new/defer disposition.
- [x] The recommendation cites project and signal evidence, shows uncertainty,
  and identifies the proposed extension seam or why none is credible.
- [x] An explicitly approved extension creates an Exploration and PRD targeted
  at the selected existing project while preserving provenance and approvals.
- [x] The user can override the recommendation and choose a greenfield project
  or defer it without corrupting prior state.
- [x] ChatGPT tools expose only bounded project assessments and enforce the
  existing confirmation token and mutation boundaries.
- [x] Offline, Postgres, and scripted conversational tests cover extension,
  greenfield, insufficient-evidence, privacy, correction, and restart cases.
- [x] A human evaluation records whether project-aware recommendations are more
  useful and grounded than new-project-only recommendations.

## Handoff

Report the matching model and weights, disposition fixtures and metrics,
target-project persistence contract, ChatGPT tool traces, approval behavior, and
the user's qualitative judgment. Any request for automatic repository changes
must become a separately approved goal.

## Execution contract

### Expected implementation surface

- Add a focused `src/riff/recommendations.py` service and migration only if a
  durable target-project reference or recommendation record cannot be represented
  by an additive relation on the existing Exploration tables.
- Extend `src/riff/adapter.py` and `src/riff/mcp_server.py` with bounded read
  tools (`list_projects`, `inspect_project`, `match_riff_to_projects`) and a
  confirmation-gated `propose_extension` operation; preserve the existing
  `riff-tools-v1` error and response bounds.
- Add `tests/fixtures/projects/` for at least one strong extension, one clear
  greenfield, one insufficient-evidence case, and contradictory/changed project
  snapshots. Add focused offline tests in `tests/test_recommendations.py` and
  Postgres/conversational coverage in the existing adapter/MCP test seams.
- Update `docs/architecture.md`, `README.md`, and a numbered decision record
  with the scoring and target-reference choices.

### Canonical contracts and invariants

- Dispositions are exactly `EXTEND_EXISTING`, `START_NEW`, or `NOT_NOW`.
- A recommendation contains `recommendation_id`, `riff_id`, `project_id` (null
  for `START_NEW`/`NOT_NOW`), `disposition`, `fit_score`, `learning_value`,
  `effort_hours`, `scope_risk`, `confidence`, `evidence_ids`,
  `project_snapshot_id`, `rationale`, `uncertainty`, `policy_version`, and
  `status` (`PROPOSED`, `OVERRIDDEN`, `ACCEPTED`, `DEFERRED`). Scores are in
  `[0,1]`; effort is bounded to 4–20 focused hours.
- `EXTEND_EXISTING` is illegal without an active project, a cited snapshot, a
  non-empty extension seam, and at least one cited Riff receipt. `START_NEW`
  must not carry a project target. `NOT_NOW` must include a missing-evidence or
  scope-risk reason. A proposed recommendation never mutates a repository,
  profile, Exploration, or PRD.
- An accepted extension stores the stable `project_id` on the Exploration/PRD
  relation; existing greenfield rows remain valid with a null target.

### Deterministic behavior matrix

| Input/evidence condition | Required result |
|---|---|
| Strong capability/seam fit and healthy active project | `EXTEND_EXISTING`, cited snapshot and seam, ranked score |
| No credible seam or project health is poor, but Riff is actionable | `START_NEW`, project target null, greenfield rationale |
| Missing snapshot, conflicting mappings, or insufficient evidence | `NOT_NOW`, explicit unknowns and next evidence request |
| Archived/disabled project | Never `EXTEND_EXISTING`; exclude or explain as unavailable |
| Repeated identical match request | Stable recommendation/input fingerprint; no duplicate mutation |
| User chooses “start new” or “defer” | Append override status/reason; preserve original recommendation |
| Model supplies a confirmation token | Ignore it; only the outer user-confirmation boundary may authorize mutation |

### Authority and side-effect boundaries

Matching reads persisted Riff receipts, profile slices, project inventories, and
snapshots only. It performs no GitHub network call, repository execution,
subprocess, credential access, model call, or repository mutation. Optional
model text may explain a deterministic result but cannot change disposition,
scores, citations, or approval status. Only explicit user confirmation may
accept an extension, create an Exploration, or approve a PRD.

### Fixtures, replay, and budgets

Fixtures must cover positive extension, greenfield, insufficient/contradictory
evidence, archived project, malformed snapshot, oversized text, and changed
snapshot/version inputs. Every fixture is offline and secret-free. Matching is
bounded to at most 5 projects, 10 receipts, 3 recommendations, 20k serialized
response bytes, and 10 seconds; identical fingerprints are cached, while a
changed project snapshot invalidates only the affected match. Restarting the
adapter loses no recommendation or target reference. No retry may repeat an
acceptance mutation.

### Criterion-to-test map

- Matching/disposition and score bounds: `tests/test_recommendations.py` fixture
  cases `extension`, `greenfield`, and `insufficient`.
- Citation/uncertainty/privacy and archived-project exclusion:
  `tests/test_recommendations.py` evidence assertions.
- Targeted Exploration/PRD and user overrides: Postgres tests in
  `tests/test_recommendations.py` plus `tests/test_explorations.py`/`tests/test_prds.py`.
- ChatGPT bounds, confirmation, restart, and stable IDs: adapter/MCP tests and
  a scripted scenario under `tests/fixtures/chat/`.
- Human usefulness/grounding comparison: a redacted report under
  `docs/reports/g27-recommendation-evaluation.md`.

## Cycle verification (2026-09-15)

- Full offline suite: **passed**; Postgres-marked tests were skipped because no
  test database URL was supplied for this cycle.
- Focused offline recommendation tests: **3 passed**.
- Human usefulness review: **complete**. The user judged project-aware output
  preferable when a legitimate, evidence-backed project seam exists, and
  greenfield preferable when project targeting would add complexity without a
  credible benefit. This is a conditional policy, not a blanket preference.
- Shared development fixture contamination remains routed to G35 and
  `BL-G27-001`; it is not treated as a recommendation-quality success.
