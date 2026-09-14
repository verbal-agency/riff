# G26 — Build an evidence-backed understanding of user GitHub projects

**Status:** Queued
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

- [ ] The user can explicitly onboard and archive a GitHub repository in a
  durable project inventory with stable provider identity.
- [ ] A bounded fixture snapshot produces a versioned, inspectable summary of
  purpose, technologies, capabilities, activity, extension seams, and unknowns.
- [ ] Every summary claim links to stored GitHub evidence and a parser/policy
  version; uncertain or inferred fields are labeled accordingly.
- [ ] Repository renames, repeated refreshes, changed content, duplicate
  artifacts, and bounded/malformed inputs behave deterministically.
- [ ] Project evidence flows through existing receipts and capability mappings
  without changing the user's profile automatically.
- [ ] Postgres persistence and offline fixture tests cover onboarding, refresh,
  inspection, privacy boundaries, and version/provenance behavior.
- [ ] Operator documentation explains approval, refresh bounds, disablement, and
  the no-execution/no-private-code boundary.

## Handoff

Report the project inventory schema, snapshot surfaces and bounds, capability
mapping behavior, fixture evidence, and unresolved understanding gaps. G27 may
consume only the compact project assessment and its cited evidence.
