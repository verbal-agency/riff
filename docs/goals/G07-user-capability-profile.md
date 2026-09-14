# G07 — Build the user's evidence-backed capability profile

**Status:** Ready
**Depends on:** G06  
**Unlocks:** G08  
**PRD references:** Sections 3, 12–14, 24.3, 25

## Outcome

Riff can answer what the user knows or demonstrates for a capability, distinguish public from private evidence, and classify the likely gap without assuming that absence from GitHub means absence of experience.

## User-visible proof

For a selected capability, the user sees evidence grouped by public portfolio/GitHub, private professional attestation, hands-on personal work, study/familiarity, and Riff-generated artifacts, followed by an uncertainty-aware gap classification.

## Inputs

- G06 capability identities and capability/technology relationships.
- User-supplied public profile locations and private Experience Ledger entries.

## Scope

- Define profile evidence with source, capability, evidence level, confidence, public/private visibility, description/reference, dates, and provenance.
- Support the PRD evidence levels: `PUBLICLY_DEMONSTRATED`, `PROFESSIONALLY_DEMONSTRATED_PRIVATE`, `HANDS_ON_PERSONAL`, `STUDIED`, `CONCEPTUALLY_FAMILIAR`, and `UNKNOWN`.
- Support manually supplied private Experience Ledger entries without requiring publication.
- Add bounded ingestion/import for configured public GitHub and website evidence, reusing the evidence pipeline where appropriate.
- Allow completed Riff artifacts to become candidate profile evidence without automatically assigning proficiency.
- Classify `KNOWLEDGE_GAP`, `IMPLEMENTATION_GAP`, `SIGNALING_GAP`, `EXPERIENCE_GAP`, `NO_MEANINGFUL_GAP`, or `UNKNOWN` with rationale and uncertainty.
- Handle corrections and semantic feedback such as “I already do this professionally.”

## Non-goals

- Résumé generation, employment verification, multi-user profiles, publishing private data, or asserting mastery from a mention alone.
- Ranking emerging signals.

## Required properties

- Private evidence is never returned by public/export views and is not logged or sent to models unless needed for the selected capability.
- Multiple evidence levels may coexist for one capability.
- User attestations are clearly labeled rather than treated as independently verified public evidence.
- Negative absence is not proof: no GitHub evidence alone cannot create a knowledge-gap conclusion.
- Gap classifications retain the evidence and rationale used and can be recomputed after corrections.

## Deliverables

- Profile-evidence and gap-assessment schema/migrations.
- Manual Experience Ledger create, update, list, and archive operations.
- Bounded public-profile evidence importer(s) sufficient for the dogfood user.
- Capability-profile query and gap-classification service.
- Privacy, correction, and sparse-evidence fixtures/tests.

## Acceptance criteria

- [ ] A capability can simultaneously show private professional evidence and no public evidence and is classified as a signaling gap, not a knowledge gap, when fixture facts support that result.
- [ ] A manual private entry is labeled `USER_ATTESTED`, excluded from public/export results, and retrievable in the authorized personal view.
- [ ] A GitHub technology mention alone does not automatically become hands-on capability proof.
- [ ] Correcting or archiving profile evidence causes the assessment to update while preserving decision history.
- [ ] A completed-project artifact enters as candidate capability evidence and requires an explicit/defined assessment before raising the profile level.
- [ ] Sparse or conflicting evidence can yield `UNKNOWN` with an explanation rather than false precision.
- [ ] The profile query loads only the requested capability slice and tests prevent private descriptions from appearing in logs or unrelated model prompts.

## Verification evidence

Use fixtures for a signaling gap, true implementation gap, GitHub-only mention, conflicting public/private evidence, and sparse unknown case. Record the evidence shown and rationale returned for each.

## Implementation latitude

The first public website input may be a bounded user-supplied URL/export or fixture-backed collector. Prioritize correct evidence semantics and privacy over broad crawling.

## Execution contract for the next Luna run

### Expected implementation surface

Extend `src/riff` with profile-evidence and gap-assessment domain records,
private Experience Ledger CRUD, a bounded public-profile importer, and a
capability-scoped assessment service over G06 entities and relationships. Add
the next numbered migration, focused tests in `tests/test_user_profile.py`,
fixtures under `tests/fixtures/profile/`, and a deterministic evaluation
command/report. Document authorized personal versus public views in `README.md`
and `docs/architecture.md`; add an ADR for any privacy or evidence-level
invariant.

### Canonical domain and persistence contract

| Concept | Required fields | Invariants |
|---|---|---|
| Profile evidence | `profile_evidence_id`, `capability_id`, `evidence_level`, `visibility`, `origin`, `confidence`, `description`, `reference`, `observed_at`, `status` | Levels are explicit; private descriptions are never returned by public/export queries. |
| Experience Ledger entry | `ledger_id`, `profile_evidence_id`, `entry_text`, `employer_or_context`, `attestation_state` | Manual entries are `USER_ATTESTED`, editable, archivable, and not independently verified. |
| Gap assessment | `assessment_id`, `capability_id`, `classification`, `rationale`, `uncertainty`, `computed_at` | Classification is recomputable from the selected evidence slice; absence alone cannot produce `KNOWLEDGE_GAP`. |
| Decision/history event | `event_id`, `target_id`, `action`, `actor`, `reason`, `created_at` | Corrections, archives, and semantic feedback append history rather than erasing prior evidence. |

Allowed evidence levels: `PUBLICLY_DEMONSTRATED`,
`PROFESSIONALLY_DEMONSTRATED_PRIVATE`, `HANDS_ON_PERSONAL`, `STUDIED`,
`CONCEPTUALLY_FAMILIAR`, and `UNKNOWN`. Allowed gap classifications:
`KNOWLEDGE_GAP`, `IMPLEMENTATION_GAP`, `SIGNALING_GAP`, `EXPERIENCE_GAP`,
`NO_MEANINGFUL_GAP`, and `UNKNOWN`.

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| Private professional evidence and no public evidence | `SIGNALING_GAP`, with private evidence visible only in the authorized personal view. |
| GitHub technology mention without capability evidence | No automatic hands-on or professional capability proof. |
| Corrected or archived evidence | Assessment changes on recomputation; prior event and provenance remain queryable. |
| Completed Riff artifact | Candidate evidence only until an explicit assessment promotes its level. |
| Sparse or conflicting evidence | `UNKNOWN` with rationale and uncertainty, never false precision. |
| Public/export query | Returns only public evidence; private text is absent from payloads and logs. |
| Capability query | Loads only the requested capability and its bounded evidence slice. |

### Authority and side-effect boundaries

This goal may read G06 capability records and mutate only the user profile,
ledger, assessment, and correction history. It must not publish private data,
infer mastery from mentions, rank signals, rewrite receipts, or send unrelated
profile/corpus data to a model. Public imports are bounded and fixture-backed by
default; credentials are process-only and model calls, if any, use an injected
replaceable interface.

### Offline fixtures and state controls

Provide signaling-gap, implementation-gap, GitHub-only, conflicting
public/private, sparse-unknown, completed-artifact, correction, archive, and
private-redaction fixtures. Verify evidence-level transitions, query slice
limits, public/private payload separation, history retention, duplicate replay,
and no-model-call behavior for deterministic assessments.

### Criterion-to-test/artifact map

| G07 criterion | Required proof artifact |
|---|---|
| Signaling gap | `test_private_without_public_is_signaling_gap` |
| Private ledger privacy | `test_user_attested_entry_is_redacted_from_public_view` |
| GitHub-only handling | `test_github_technology_mention_is_not_hands_on_proof` |
| Correction/archive history | `test_correction_and_archive_recompute_with_history` |
| Completed artifact candidate | `test_completed_artifact_requires_explicit_assessment` |
| Sparse/conflicting unknown | `test_sparse_conflicting_evidence_is_unknown` |
| Scoped query and redaction | `test_profile_query_is_capability_scoped_and_redacted` |
