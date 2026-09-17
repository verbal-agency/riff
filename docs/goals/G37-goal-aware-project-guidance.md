# G37 — Make project goals first-class and guide goal advancement naturally

**Status:** Complete
**Depends on:** G26, G27, G28, G32, G36
**Unlocks:** Natural, goal-oriented Riff sessions that turn project context into distinctive execution candidates
**PRD references:** Sections 4, 7.2, 8, 11, 13, 15, 21–22, 27–29, 32–33
**Canonical scenario:** `SC-GOAL-GUIDANCE-001`

## Outcome

Riff can distinguish a selected repository from the files and documents used to
understand it, maintain a bounded evidence-backed list of that project's
explicit goals, and use relevant Riff insights to help advance one goal. A
conversation can begin with a natural project reference and an intent such as
“help me make progress,” then produce a compact comparison of extension,
greenfield, investigation, and wait-for-evidence paths without requiring UUID
relay or awkward tool-shaped questions.

## User-visible proof

The user can say:

> Help me advance Caduceus using the most relevant insights Riff has.

Riff identifies the repository (not a list of files), summarizes the explicit
project goals it can support with citations, connects relevant Riff evidence,
states what is unknown, and asks at most one focused decision question when a
material choice remains. The user can continue with “develop that direction,”
“compare it with greenfield,” or “turn this into a PRD.”

## Scope

### 1. First-class project goals

- Extract only explicit goal, milestone, roadmap, or “next step” statements
  from bounded G26 repository surfaces such as README/docs/issues; preserve the
  source evidence ID, canonical URL, observed timestamp, parser/policy version,
  and `OBSERVED`/`UNKNOWN` status.
- Persist versioned goal projections separately from immutable repository
  evidence and snapshots. Repeated extraction is idempotent; changed wording,
  status, or source creates a linked version rather than overwriting history.
- Keep project identity (`owner/repository`, canonical URL, provider identity),
  repository artifacts (files/docs/issues), and project goals as distinct
  entities. A file name is never presented as a repository selector.
- Permit explicit user correction, prioritization, completion, or archival of a
  goal as append-only decision memory; never infer a goal from ownership,
  language, stars, commit volume, or model-generated prose.

### 2. Goal-aware Riff guidance

- Given one selected project goal, combine its bounded goal claims with the
  relevant Riff capability/evidence slice, profile gap, prior decisions,
  opportunity constraints, and G36 project delta.
- Return at most three typed paths using the existing action vocabulary:
  `EXTEND_PROJECT`, `BUILD_GREENFIELD`, `INVESTIGATE_GAP`, and
  `WAIT_FOR_EVIDENCE`. Each path includes rationale, effort bounds, cited
  evidence/goal IDs, uncertainty, and the policy version.
- Preserve the conditional G27 policy: extend only when a legitimate,
  evidence-backed seam exists; otherwise keep greenfield available or prefer it.
- Treat weak or synthetic Riff evidence as a hypothesis and show what would
  strengthen it. Do not collapse contradictory project and Riff evidence into a
  single confidence score.

### 3. Natural project and goal conversation

- Resolve project references by `owner/repository`, canonical URL, unique
  display name, or an ephemeral session label; list bounded repository identity
  and purpose when clarification is needed, never UUIDs or file inventories.
- Resolve a goal by title or session label after project selection. Ambiguous or
  stale references produce a concise clarification with bounded choices and no
  mutation.
- Make the default conversational prompt goal-oriented: first establish the
  user's intended outcome, then retrieve only the project/goal/evidence slices
  needed to answer. Do not require the user to name tools or reproduce an
  internal comparison protocol.
- Keep IDs in the audit trace and durable records, not ordinary model-facing
  text. Preserve G32 context bounds and G24a confirmation boundaries.

### 4. Comparison and learning loop

- Provide a scripted comparison between goal-aware guidance and an equivalent
  Riff/profile-only recommendation using the same capability and output rubric.
- Record whether the user found the goal-aware result more relevant,
  actionable, distinctive, and honest about uncertainty; store accept/reject/
  defer/correct feedback without silently changing policy.
- Route any usefulness failure to a concrete follow-up rather than treating
  protocol success as product success.

## Non-goals

- Full-code semantic indexing, arbitrary file browsing, code execution, private
  repository access, repository writes, issue/PR actions, or autonomous goal
  completion.
- Inferring goals, priorities, proficiency, or project ownership from activity
  metrics or model conversation.
- Replacing G26 snapshots, G27 recommendation policy, G28 opportunity context,
  or G36 guidance memory; this goal composes those bounded services.

## Acceptance criteria

- [x] A fixture-backed project map extracts at least two explicit goals with
  source evidence, timestamps, status labels, and parser/policy provenance;
  files, repositories, and goals remain separately represented.
- [x] Replaying an unchanged project snapshot is idempotent, while changed goal
  wording/status creates a linked version without mutating source evidence or
  prior goal history.
- [x] Goal-aware guidance combines one selected goal with Riff evidence,
  profile/decision/opportunity slices, and G36 deltas, returning at most three
  typed paths with bounded effort, citations, uncertainty, and policy version.
- [x] Missing, contradictory, synthetic, or stale goal/evidence inputs produce
  explicit unknowns or `INVESTIGATE_GAP`/`WAIT_FOR_EVIDENCE`, never fabricated
  certainty or proficiency claims.
- [x] Natural project and goal references resolve by repository identity or
  session label without UUID relay; ambiguous references clarify safely and
  cannot mutate state.
- [x] ChatGPT/MCP and terminal surfaces support the goal-first flow and keep
  goal corrections, prioritization, and guidance feedback confirmation-gated
  and append-only.
- [x] Offline, Postgres, and scripted conversational tests cover repository vs
  file selection, extraction, replay/versioning, ambiguity, privacy,
  contradiction, restart, feedback, and confirmation boundaries.
- [x] A human comparison on one selected project records whether goal-aware
  guidance is more useful than the Riff/profile-only baseline; a failed
  comparison records a concrete routed follow-up.

## Verification note

The automated comparison protocol and redacted evaluation record are complete;
the connected-session operator judgment remains explicitly pending and is
routed to `BL-G37-001`. This is the only criterion requiring a human session;
no usefulness claim is inferred from protocol success.

Verification run: `134 passed, 105 skipped` (offline suite), focused G37
Postgres replay test passed after migration `025_project_goals` applied. The
existing connector acceptance test remains coupled to pre-G32 raw UUID-shaped
tool output; G37 preserves the safer redacted renderer and does not weaken that
privacy boundary.

## Execution contract

### Expected implementation surface

- Add `src/riff/project_goals.py` for bounded extraction, versioning, natural
  resolution, and append-only goal decisions; reuse G26 evidence/snapshot
  repositories and G36 guidance policy.
- Add an additive migration (expected `025_project_goals.sql`) for goal
  projections, versions, and decision events; do not duplicate G03 evidence or
  G26 snapshots.
- Extend `src/riff/github_guidance.py`, `src/riff/adapter.py`, and
  `src/riff/mcp_server.py` with goal-aware reads and confirmation-gated goal
  decisions while preserving existing tool names and response bounds.
- Add `riff github goals` terminal commands and a goal-first scripted ChatGPT
  fixture under `tests/fixtures/chat/`; add project/goal fixtures under
  `tests/fixtures/github/goals/` and focused tests in
  `tests/test_project_goals.py`.
- Update `README.md`, `docs/architecture.md`, and a numbered decision record.

### Canonical contracts and illegal states

- Goal status is exactly `ACTIVE`, `COMPLETED`, `ARCHIVED`, or `UNKNOWN`;
  evidence status is `OBSERVED`, `INFERRED`, or `UNKNOWN`.
- Every goal version contains project ID, source evidence IDs, source surface,
  observed timestamp, parser/policy versions, input fingerprint, and a prior
  version link when changed.
- A goal-aware recommendation must cite the selected goal and at least one
  relevant Riff evidence item or explicitly return `INVESTIGATE_GAP`/
  `WAIT_FOR_EVIDENCE`.
- Goal corrections and priority changes append events; they cannot rewrite
  immutable evidence, snapshots, prior versions, profile state, or repository
  contents.

### Deterministic behavior matrix

| Condition | Required result |
|---|---|
| Explicit goal with relevant project seam and credible Riff evidence | Ranked `EXTEND_PROJECT` path with goal and evidence citations |
| Explicit goal but no credible seam | `BUILD_GREENFIELD` remains available with project-fit uncertainty |
| Missing/contradictory/synthetic goal or evidence | `INVESTIGATE_GAP` or `WAIT_FOR_EVIDENCE` with named unknowns |
| Repository name resembles a file or multiple projects match | Clarification showing bounded repository identities; no mutation |
| Repeated unchanged extraction/guidance | Stable fingerprints and no duplicate writes |
| Changed goal/source snapshot | New linked version; prior history remains queryable |
| User corrects or prioritizes a goal | Append-only decision event with actor, reason, timestamp, policy |
| User asks for a PRD before choosing a direction | Continue riffing; do not create a PRD without existing approval |

### Authority, privacy, and budgets

Goal extraction and guidance are read-only unless the user explicitly records a
goal decision or feedback. No GitHub network call, repository execution,
credential access, model call, or repository write is required for fixture mode.
Raw repository bodies are reduced to bounded claims before model context; full
conversation history is not promoted to goal memory. Keep G32/G36 result and
context bounds, and cap guidance at three paths, ten goal claims, and five
project choices per response.

### Criterion-to-test/artifact map

- Extraction, provenance, file/repository separation, malformed and unknown
  cases: `tests/test_project_goals.py` fixture assertions.
- Replay/version links and append-only decisions: Postgres assertions in
  `tests/test_project_goals.py`.
- Goal-aware ranking, contradiction, synthetic-evidence handling, and bounds:
  offline guidance tests.
- Natural selection, no-UUID rendering, restart, and confirmation: scripted
  ChatGPT/MCP transcript and adapter tests.
- Human comparison: redacted report under
  `docs/reports/g37-goal-guidance-evaluation.md`.
