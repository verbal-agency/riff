# G26 — Build an evidence-backed understanding of user GitHub projects

**Status:** Complete
**Depends on:** G03, G22, G25
**Unlocks:** Project-aware opportunity matching and extension recommendations
**PRD references:** Sections 7.2, 8, 11, 13, 21, 27, 33
**Canonical scenario:** `SC-PROJECT-MAP-001`

## Outcome

Riff can maintain a user-approved inventory of GitHub projects and summarize
what each project is for, what capabilities and technologies it demonstrates,
how mature or active it appears, and where new capabilities could fit. The
understanding is versioned, evidence-backed, and uncertainty-aware; it is not a
claim that the user personally possesses every capability visible in a repo.

## User-visible proof

The user can select repositories, inspect a project summary with supporting
GitHub evidence, see detected extension seams and unknowns, and refresh the
summary after repository changes without losing prior snapshots.

## Scope

### 1. Project inventory and identity

- Add an explicit user-owned project inventory linked to stable GitHub provider
  repository IDs, with display name, purpose, status, visibility, and review
  metadata.
- Keep this inventory distinct from generated Riff `projects`/PRDs; a repository
  may be an existing target for multiple Explorations or project versions.
- Preserve rename/transfer history and explicit user archive/disable decisions.

### 2. Bounded project snapshots

- Collect only approved public repository surfaces: metadata, README/docs,
  manifests and lockfiles, directory/tree summaries, CI configuration,
  releases, and selected issues/activity within declared bounds.
- Use static parsing only; never execute repository code, install dependencies,
  clone private content, or follow arbitrary links.
- Produce versioned snapshots with retrieval timestamps, source evidence IDs,
  parser versions, and explicit missing/unknown fields.

### 3. Capability and extension model

- Map snapshot evidence to existing capability and technology entities through
  the receipt/normalization contracts, preserving candidate versus accepted
  mappings and confidence.
- Record project-level purpose, demonstrated capabilities, technologies,
  activity/maturity indicators, open seams, constraints, and uncertainty as a
  recomputable assessment rather than overwriting raw evidence.
- Distinguish observed repository facts from user-attested experience and from
  model hypotheses.

### 4. Inspection and regression coverage

- Add repository operations and fixtures for onboarding, refresh, rename,
  malformed/oversized inputs, duplicate evidence, and changed snapshots.
- Provide a compact project inspection report suitable for later ChatGPT tool
  results without exposing unrelated code or private profile data.
- Verify repeated snapshots are idempotent and changed source content creates a
  new version with provenance to the prior snapshot.

## Non-goals

- Full codebase semantic indexing, embeddings, code execution, CI execution, or
  claims of code correctness/security.
- Inferring private work history or treating repository presence as proof of
  proficiency.
- Matching opportunities or generating targeted PRDs; those belong to G27.

## Acceptance criteria

- [x] The user can explicitly onboard and archive a GitHub repository in a
  durable project inventory with stable provider identity.
- [x] A bounded fixture snapshot produces a versioned, inspectable summary of
  purpose, technologies, capabilities, activity, extension seams, and unknowns.
- [x] Every summary claim links to stored GitHub evidence and a parser/policy
  version; uncertain or inferred fields are labeled accordingly.
- [x] Repository renames, repeated refreshes, changed content, duplicate
  artifacts, and bounded/malformed inputs behave deterministically.
- [x] Project evidence flows through existing receipts and capability mappings
  without changing the user's profile automatically.
- [x] Postgres persistence and offline fixture tests cover onboarding, refresh,
  inspection, privacy boundaries, and version/provenance behavior.
- [x] Operator documentation explains approval, refresh bounds, disablement, and
  the no-execution/no-private-code boundary.

## Handoff

Report the project inventory schema, snapshot surfaces and bounds, capability
mapping behavior, fixture evidence, and unresolved understanding gaps. G27 may
consume only the compact project assessment and its cited evidence.

## Cycle verification (2026-09-15)

Implemented `src/riff/project_map.py` with the `github_project_inventory` and
`github_project_snapshots` persistence contract in migration
`018_github_project_maps.sql`. Explicit onboarding requires an existing public
G03 repository identity and records reviewer metadata; archive is a durable
status transition. Refresh reads at most 200 persisted G03 artifacts, produces
compact purpose/capability/technology/activity/extension/unknown claims, and
stores evidence, receipt, mapping, parser, and policy references without raw
repository content. Input hashes make unchanged refreshes idempotent; changed
inputs create a new version linked to the prior snapshot.

The CLI commands are `github project onboard|refresh|inspect|archive`, and the
compact inspection report is available at `GET /github/projects/{project_id}`.
Decision 0012 records the identity, bounded-surface, and uncertainty choices.

### Criterion status

- **Pass:** onboarding and archive persist a user-reviewed inventory keyed by
  stable `provider_repository_id`; archived projects cannot be refreshed.
- **Pass:** the recorded G03 fixture produces an inspectable versioned summary
  with purpose, release/issue activity, open issue extension seams, and
  explicit unknowns.
- **Pass:** every emitted claim contains evidence IDs plus parser/policy
  versions; receipt-backed capability/technology claims also retain mapping and
  receipt IDs and their proposed/accepted status.
- **Pass:** repeated refreshes reuse the same snapshot; changed repository
  metadata creates version 2 with `previous_snapshot_id`; G03 aliases remain
  available for rename history and malformed/oversized inputs remain bounded by
  the upstream collector.
- **Pass:** project summaries are derived from stored GitHub evidence and do
  not update the user capability profile; inferred text matches are explicitly
  labeled `INFERRED`.
- **Pass:** `tests/test_project_map.py` exercises Postgres onboarding, refresh,
  idempotency, changed-content versioning, inspection history, and archive
  behavior; the focused file passes 2 tests and the finalized full suite passes
  **206 tests** with 2 known dependency deprecation warnings.
- **Pass:** README documents approval, refresh bounds, archive/disablement, and
  the no-execution/no-private-code boundary.
