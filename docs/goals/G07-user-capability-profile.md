# G07 — Build the user's evidence-backed capability profile

**Status:** Queued  
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
