# G09 — Construct and publish zero to three daily Riffs

**Status:** Queued  
**Depends on:** G08  
**Unlocks:** G10, G13  
**PRD references:** Sections 4, 8.5, 9–10, 21–23, 28–29, 33

## Outcome

Riff deeply analyzes only the strongest bounded candidate set and publishes zero to three evidence-backed, personalized arguments that clearly separate observation, hypothesis, and recommendation and include the strongest countercase.

## User-visible proof

“What are today’s Riffs?” returns at most three complete arguments—or an honest no-strong-Riffs result—with clickable/inspectable provenance for every meaningful evidence-backed claim.

## Inputs

- Ranked, explained candidates and supporting/counter evidence from G08.
- Relevant G06–G07 capability/profile slices and a replaceable strong-reasoning client.

## Scope

- Define deep-analysis and published-Riff records using the PRD Riff fields and statuses.
- Select an approximately top-five configurable candidate set for strong-model reasoning.
- Retrieve only relevant receipts, capability/profile slices, and prior decisions.
- Construct claim, why now, why it matters, supporting evidence, counterevidence, strongest counterargument, alternative explanation, user relevance, underlying capability, associated technologies, recommendation, confidence, and falsification conditions.
- Validate all evidence citations against eligible stored evidence IDs.
- Apply a publication gate and a hard limit of three; allow zero.
- Version prompts/policies/models and make unchanged daily reruns idempotent.
- Present a stable daily result through the application API, independent of ChatGPT formatting.

## Non-goals

- Exploration/PRD creation, user decision handling, general chat, or fabricating balance when no real counterevidence exists.
- Sending the entire corpus or user profile to the reasoning model.

## Required properties

- Published factual observations cite evidence IDs; hypotheses and recommendations are labeled as such.
- Supporting citations actually support the associated statement.
- Source diversity and independence are visible rather than replaced by a single confidence number.
- A counterargument, plausible alternative explanation, and falsification conditions are mandatory.
- Model failure or weak candidates can reduce output count but cannot lower the quality gate to fill a quota.

## Deliverables

- Deep-reasoning provider interface and deterministic fake/recorded implementation for tests.
- Riff schema, validation, publication gate, daily query, and presentation DTO.
- Provenance/citation validation and bounded-context assembly.
- Golden cases for publish-three, publish-one, publish-zero, invalid citation, weak counterargument, and signaling-gap personalization.

## Acceptance criteria

- [ ] Published results contain zero to three Riffs and never exceed three even if more candidates are analyzed.
- [ ] Every Riff has all PRD argument fields, including counterargument, alternative explanation, and falsification conditions.
- [ ] Each evidence-backed observation and claim resolves to stored Evidence Receipts and ultimately raw evidence; an unknown or ineligible ID blocks publication.
- [ ] A fixture with no candidate above the quality threshold publishes zero and gives a non-fabricated empty-result explanation.
- [ ] Personal relevance distinguishes knowledge/implementation gaps from signaling gaps and recommends an appropriate intervention.
- [ ] Context-assembly tests prove only candidate-relevant receipts, profile slices, and decisions are sent to the deep-reasoning interface.
- [ ] Identical date, inputs, and generation-policy version do not create duplicate published Riffs or repeat model calls unnecessarily.
- [ ] Golden-case review output makes observation, hypothesis, and recommendation visually/structurally distinct.

## Verification evidence

Run the golden suite and show the zero-, one-, and three-Riff results, citation validation failure, context item counts, and model-call counts on idempotent rerun. Human review should assess argument coherence but is not yet the final dogfood gate.

## Implementation latitude

The deep model and prompt shape are replaceable. Prefer structured generation followed by deterministic validation and rendering over accepting free-form output as persisted truth.
