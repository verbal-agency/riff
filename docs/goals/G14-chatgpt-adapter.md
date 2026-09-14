# G14 — Expose Riff through a conversational ChatGPT adapter

**Status:** Queued  
**Depends on:** G10, G11, G12, G13  
**Unlocks:** G15  
**PRD references:** Sections 4, 10, 15, 27, 32–33

## Outcome

ChatGPT can act as Riff's initial conversational interface through a thin adapter over the application API, supporting daily Riffs, evidence investigation, decisions, Explorations, and PRD generation without becoming the system of record.

## User-visible proof

The user can ask “What are today’s Riffs?”, challenge an argument, inspect its evidence, record a reasoned decision, explicitly create/refine an Exploration, and explicitly approve a PRD—all against persistent Riff state.

## Inputs

- Stable application operations from G10–G13 and their approval/actor contracts.
- The supported ChatGPT integration protocol and deterministic local fixture state.

## Scope

- Implement a documented ChatGPT-compatible tool surface (for example MCP or the current supported equivalent) over application operations.
- Provide operations corresponding to daily Riffs, investigation/search, capability/profile lookup, decision recording, Exploration creation/update/select, and PRD generation/export.
- Return structured payloads designed for concise conversational rendering with evidence IDs and source links.
- Preserve explicit user-confirmation requirements at both promotion boundaries even if the conversational model calls tools incorrectly.
- Add installation/configuration/run documentation and a scripted conversation acceptance harness.
- Ensure adapter failures do not alter core state outside an operation's transaction.

## Non-goals

- Reimplementing domain logic in prompts, storing canonical state in ChatGPT history, a complex frontend, broad assistant memory, or autonomous coding.

## Required properties

- The adapter is thin: product rules and approvals are enforced by the application layer.
- Read operations expose only the minimum relevant profile/evidence slice.
- Mutating operations have explicit schemas and return resulting persistent identity/status.
- Approval tools require an explicit user-originated confirmation token/event; descriptive model text alone is insufficient.
- The core API remains usable without the adapter.

## Deliverables

- ChatGPT-compatible adapter/tool server and typed operation schemas.
- Concise result DTOs and source/evidence link behavior.
- Configuration and connection guide.
- Scripted conversational acceptance cases and error/approval tests.

## Acceptance criteria

- [ ] “What are today’s Riffs?” returns the persisted daily zero-to-three result rather than generating an untracked answer in the adapter.
- [ ] The user can ask for strongest evidence, counterevidence, profile gap, companies/sources, and raw provenance for a chosen Riff.
- [ ] Reject/watch/archive actions persist the user's semantic reason and return the resulting lifecycle state.
- [ ] No tool-call sequence lacking explicit user approval can create an Exploration or PRD.
- [ ] With approvals, a scripted flow reaches Riff -> Exploration -> selected experiment -> PRD/export and every object retains provenance.
- [ ] An adapter restart loses no canonical product state.
- [ ] Tool payloads omit unrelated private profile evidence and tests cover accidental overfetch/leakage.
- [ ] The adapter can be installed and exercised locally using only documented steps and deterministic fixture data.

## Verification evidence

Record scripted happy-path, rejection, zero-Riff, invalid approval, missing evidence, and restart flows. Include created object IDs/statuses and prove the same state is queryable directly through the application API.

## Implementation latitude

Use the ChatGPT integration mechanism that is supported when this goal is implemented. Keep it replaceable and document any platform-specific assumptions; the PRD deliberately keeps the underlying application interface-agnostic.
