# G36 — Turn monitored GitHub changes into personalized guidance and durable memory

**Status:** Queued
**Depends on:** G26, G27, G32, G33, G34, G35
**Unlocks:** Evidence-backed, account-aware guidance about what to build or learn next
**PRD references:** Sections 4, 7.2, 8, 11, 13, 15, 21–22, 27–29, 32–33
**Canonical scenario:** `SC-PERSONALIZED-GITHUB-001`

## Outcome

Riff can monitor a user-selected GitHub repository, explain meaningful changes
in the context of that project's bounded understanding, and produce
personalized guidance without confusing repository facts with personal
proficiency. Guidance is reproducible from a durable memory graph whose
components have explicit provenance, confidence, correction history, and
retention rules.

## User-visible proof

The user can ask “what changed in my repo and what should I do next?” and get a
compact answer that cites the new evidence, compares it with prior project
snapshots, identifies a relevant capability gap or extension seam, and offers
bounded next actions. The user can correct the interpretation, accept or reject
the guidance, and later see why a recommendation changed. No UUID relay or
full conversation export is required.

## Scope

### 1. Repository delta analysis

- Consume only explicitly selected G34 watch runs and G26 project snapshots.
- Compute deterministic deltas for bounded metadata, README/docs, releases,
  issues, manifests, and other approved surfaces; distinguish new, changed,
  removed, duplicate, and unavailable evidence.
- Summarize deltas as observed facts with source evidence IDs, timestamps,
  parser/policy versions, and uncertainty. Never infer proficiency from a
  commit, language, star, ownership, or activity count.
- Compare a repository delta with current Riff capabilities, profile gaps,
  prior decisions, and opportunity constraints to identify extension seams,
  greenfield alternatives, and “not enough evidence” outcomes.

### 2. Explicit memory architecture

Persist five bounded layers with separate schemas and lifecycle rules:

1. **Evidence ledger** — immutable G03/G34 evidence and retrieval history.
2. **Project understanding** — immutable G26 snapshots and deterministic delta
   projections; facts are labeled observed, inferred, or unknown.
3. **User decision memory** — append-only corrections, approvals, rejections,
   priorities, and rationale with actor, timestamp, and evidence snapshot.
4. **Guidance memory** — versioned recommendation inputs/outputs, cited
   evidence, uncertainty, user outcome, and supersession links.
5. **Conversation context** — disposable G32 handles and recent turns only;
   never promoted to canonical memory without an explicit decision record.

- Use stable entity IDs plus content/policy fingerprints to make replays
  idempotent and changed inputs create new versions rather than overwrites.
- Keep raw repository bodies out of guidance/model context by default; expose
  bounded excerpts or claims only when their evidence links are retained.
- Define retention, correction, archival, and deletion semantics per layer;
  preserve provenance when a derived memory item is superseded or quarantined.

### 3. Personalized guidance and feedback

- Add a deterministic guidance service that ranks at most three next actions by
  relevance to the selected project, evidence quality, user-stated priorities,
  effort, learning value, and uncertainty.
- Offer distinct action types: `EXTEND_PROJECT`, `BUILD_GREENFIELD`,
  `INVESTIGATE_GAP`, and `WAIT_FOR_EVIDENCE`.
- Require explicit user confirmation before durable project selections,
  Exploration creation, or changes to profile state. Guidance itself remains a
  read result until the user records feedback.
- Record whether guidance was accepted, rejected, deferred, or corrected, and
  use that feedback only to alter later ranking through an inspectable policy
  version—not opaque model memory.

### 4. ChatGPT and operator surfaces

- Add bounded read tools for repository changes, project memory inspection, and
  personalized guidance; add confirmation-gated feedback recording.
- Support natural-language repository/project references from G32/G33 context,
  with clarification on ambiguity and no stable-ID requirement for normal use.
- Provide terminal and cron-compatible commands to inspect deltas, explain
  guidance inputs, record feedback, and export a redacted memory audit.

## Non-goals

- Full-code semantic indexing, embeddings, code execution, private repository
  access, repository writes, issue/PR actions, or autonomous project changes.
- Treating monitoring volume or ownership as capability proof.
- Persisting unrestricted conversation history or silently learning preferences
  from model-generated text.
- Replacing G26 project snapshots, G27 recommendation policy, or G34 watches.

## Acceptance criteria

- [ ] A selected repository's monitored fixture delta produces deterministic
  observed/changed/unknown claims with evidence, timestamps, and policy
  provenance.
- [ ] Guidance compares a delta with the bounded project map, profile gap,
  decisions, and opportunity context and returns at most three typed actions
  with rationale, uncertainty, and cited evidence.
- [ ] The five memory layers remain separately queryable; derived guidance and
  user corrections never mutate immutable evidence or project snapshots.
- [ ] Replaying an unchanged watch run is idempotent; changed evidence creates
  a new delta/guidance version linked to its predecessor.
- [ ] User feedback can accept, reject, defer, or correct guidance and later
  ranking exposes the policy/version and the feedback it used.
- [ ] ChatGPT and terminal surfaces return bounded, redacted guidance and
  memory audits, resolve natural-language project references safely, and keep
  durable mutations confirmation-gated.
- [ ] Offline, Postgres, and scripted conversational tests cover new/changed/
  duplicate/unavailable evidence, contradictory signals, privacy, replay,
  correction, retention, restart, and confirmation boundaries.
- [ ] Operator dogfood on one explicitly selected repository confirms that the
  guidance is more useful than an unpersonalized recommendation, or records a
  routed follow-up if the comparison fails.

## Execution contract

### Expected implementation surface

- Add `src/riff/github_guidance.py` for delta projection, memory-layer reads,
  guidance ranking, and feedback transitions; reuse G26/G27/G34 repositories.
- Add additive migrations only for delta projections, guidance versions, and
  append-only feedback; do not duplicate G03 evidence or G26 snapshots.
- Extend `src/riff/adapter.py`/`src/riff/mcp_server.py` and add CLI commands
  under `riff github guidance`; add fixtures under
  `tests/fixtures/github/guidance/` and focused tests in
  `tests/test_github_guidance.py`.
- Update `README.md`, `docs/architecture.md`, and a numbered memory-policy
  decision record.

### Canonical contracts and illegal states

- Delta status is `NEW`, `CHANGED`, `UNCHANGED`, `DUPLICATE`, or `UNAVAILABLE`;
  guidance actions are exactly `EXTEND_PROJECT`, `BUILD_GREENFIELD`,
  `INVESTIGATE_GAP`, or `WAIT_FOR_EVIDENCE`.
- Every delta and guidance version contains input fingerprints, source evidence
  IDs, project snapshot ID, policy/parser versions, uncertainty, and a prior
  version link when applicable.
- Guidance cannot claim proficiency, mutate profile state, or create an
  Exploration. Feedback cannot rewrite evidence or project snapshots.
- Conversation context is never durable memory unless an explicit user
  decision records the promoted fact, scope, rationale, and evidence snapshot.

### Behavior and test map

| Condition | Required result |
|---|---|
| New release or issue in watched repo | One `NEW`/`CHANGED` delta and cited guidance |
| Unchanged repeat | Existing delta/guidance version; no duplicate writes |
| Duplicate/correlated evidence | Labeled duplicate; no confidence inflation |
| Missing or inaccessible surface | `UNAVAILABLE`/`UNKNOWN`; no fabricated claim |
| Conflicting project and Riff evidence | `INVESTIGATE_GAP` or `WAIT_FOR_EVIDENCE` with both citations |
| User correction | Append-only feedback and a new policy input version |
| Ambiguous natural-language project | Clarification; no mutation |
| Confirmed durable action | Existing approval boundary is invoked exactly once |

Map each row to named offline/Postgres assertions in
`tests/test_github_guidance.py`, a scripted ChatGPT transcript, and a redacted
operator memory-audit artifact. The final operator comparison is a human
evaluation and must remain separate from protocol correctness.
