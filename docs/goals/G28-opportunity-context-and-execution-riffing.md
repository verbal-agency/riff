# G28 — Model opportunity context and riff on execution candidates

**Status:** Ready
**Depends on:** G21, G24, G26, G27
**Unlocks:** Distinctive applied-AI demonstrators
**PRD references:** Sections 3–6, 7, 9, 11–15, 18–21, 27–33
**Canonical scenario:** `SC-EXECUTION-RIFF-001`

## Outcome

Riff can understand the basic constraints of a target opportunity before
suggesting what to build. Given a role, product, or customer-workflow source,
it extracts the relevant users, workflows, platform primitives, data sources,
connectors, permissions, approvals, security concerns, success measures, and
unknowns. It then compares that context with the user's capability profile and
existing projects, generates several credible execution candidates, and
iteratively riffs on those candidates to find a more distinctive project.

The result is an implementation-ready direction chosen by the user, not a
literal job application and not an automatically selected generic demo.

## User-visible proof

The user can provide a target opportunity URL such as a job listing. Riff shows
the extracted opportunity context and its evidence, calls out obvious platform
and workflow requirements (including Perplexity Computer when the source names
it), identifies personal gaps and existing-project leverage, and presents a
lineage of execution candidates. The user can ask Riff to combine, extend,
narrow, invert, or otherwise transform a candidate, compare the resulting
directions, and choose one for a later Exploration/PRD.

## Scope

### 1. Opportunity context and constraint model

- Accept a permitted role, product, or customer-workflow URL plus deterministic
  fixture input for offline evaluation.
- Extract actors, jobs-to-be-done, workflow stages, data and tool surfaces,
  platform primitives, connectors, permissions, approvals, security boundaries,
  operational constraints, success measures, and unresolved questions.
- Represent named platforms and products as context and constraints rather than
  treating them as an automatic implementation choice. Perplexity Computer is a
  required fixture example, not a hard-coded dependency for every opportunity.
- Preserve source receipts, citations, extraction confidence, and explicit
  unknowns; a single listing must not become a capability conclusion.

### 2. Candidate generation

- Generate a small family of technically credible execution candidates from the
  opportunity context, user capability gaps, prior decisions, and approved
  GitHub project assessments.
- Each candidate records its thesis, target user/problem, required capabilities,
  platform role, proposed extension seam or greenfield boundary, deliverables,
  evaluation measures, risks, and expected evidence of competence.
- Include at least one existing-project extension when a credible seam exists
  and one greenfield alternative when the evidence supports both.
- Keep candidate creation separate from Exploration and PRD approval.

### 3. Iterative execution riffing

- Provide explicit transformations such as `COMBINE`, `EXTEND`, `NARROW`,
  `INVERT`, `TRANSFER`, and `CONSTRAIN`.
- Preserve parent/child lineage, the context and evidence used, the changed
  assumptions, and the reason each variant may be more distinctive.
- Support at least two bounded riffing rounds over a fixture candidate set and
  compare variants on feasibility, distinctiveness, personal fit, learning
  value, evidence value, scope risk, and expected customer usefulness.
- Surface multiple strong directions and counterarguments; never silently
  collapse the search to the first plausible project.

### 4. Conversation and handoff

- Expose compact, bounded operations through the existing conversational adapter
  for inspecting context, listing candidates, riffing on a candidate, comparing
  variants, and recording the user's chosen direction.
- Keep repository, profile, and source data minimized to the relevant slices;
  do not expose private or unrelated evidence.
- Produce an implementation-ready brief containing the selected direction,
  alternatives considered, rationale, constraints, acceptance measures, and the
  next human approval required to create an Exploration or PRD.

### 5. Evaluation

- Add fixtures for the Perplexity Computer role, a comparable platform role, an
  incomplete opportunity, and an opportunity where extending an existing
  project is clearly better than starting over.
- Measure extraction coverage, obvious-constraint recall, candidate diversity,
  lineage integrity, extension/new-project disposition, citation coverage,
  novelty rationale, and user override behavior.
- Include failure cases for malformed or inaccessible URLs, unsupported claims,
  missing context, privacy boundaries, repeated riff requests, and attempts to
  create a project without explicit approval.

## Non-goals

- Producing resumes, cover letters, or other literal job-application material.
- Automatically choosing or implementing a project, modifying repositories,
  committing code, deploying workflows, or sending external messages.
- Assuming Perplexity Computer, ChatGPT, or any other platform is the answer for
  every opportunity; platform execution belongs to a later, explicitly selected
  project.
- Replacing the existing evidence, capability, profile, project-understanding,
  or human-approval contracts.

## Acceptance criteria

- [ ] A permitted opportunity fixture produces a versioned context record with
  actors, workflow, platform, data, permission, approval, security, success,
  and unknown fields, each linked to evidence or marked uncertain.
- [ ] The Perplexity Computer fixture identifies Computer as an opportunity
  constraint without making it a universal implementation requirement.
- [ ] Riff generates at least three materially different execution candidates
  and includes extension/new-project alternatives when justified.
- [ ] Two bounded riffing rounds produce traceable variants using named
  transformations, with rationale and comparison scores.
- [ ] The user can inspect candidates, request another riff, compare variants,
  and record a chosen direction without creating an Exploration or PRD.
- [ ] The resulting brief names a real artifact, evaluation plan, risks,
  expected capability evidence, and the next approval boundary.
- [ ] Offline, Postgres, and conversational tests cover extraction, omission
  detection, candidate diversity, lineage, privacy, malformed input, restart,
  and approval behavior.
- [ ] Human evaluation records whether the riffed direction is more distinctive
  and more personally meaningful than the initial candidates.

## Handoff

Report the opportunity-context schema, extraction and uncertainty policy,
candidate and lineage model, transformation operators, comparison metrics,
conversation traces, and the user's qualitative judgment. Any implementation of
the chosen demonstrator becomes a separately scoped goal.
