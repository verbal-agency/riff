# Riff v0.1 implementation goals

This roadmap translates the [Riff v0.1 PRD](../../Riff%20v0.1%20Product%20Requirements%20Document.md) into bounded goals that an implementation agent can execute one at a time. The PRD remains the product authority; these files define delivery order and verifiable slices.

## How 5.6 Luna should consume this roadmap

1. Read the PRD, this file, and exactly one active goal before changing code.
2. Inspect the current repository and preserve already-completed behavior.
3. Implement the smallest coherent solution that meets the active goal's acceptance criteria.
4. Make local implementation decisions when the goal intentionally leaves them open. Record consequential or hard-to-reverse decisions in `docs/decisions/`.
5. Do not pre-build later goals. Stable interfaces, migrations, and small enabling seams are allowed when required by the active goal.
6. Verify every acceptance criterion with automated evidence where possible. State any criterion requiring human judgment explicitly.
7. End with a concise handoff: changed files, decisions, verification run, acceptance status, and material follow-ups.

If a goal conflicts with the PRD, stop and surface the conflict instead of silently redefining the product. If implementation uncovers useful work outside the active goal, record it as a follow-up rather than expanding scope.

## Invariants across every goal

- Riff has one user in v0.1 and no authentication or team model.
- It is one Python application backed by Postgres, with one scheduled worker and a small interface-agnostic application API.
- Raw evidence is collected once and remains traceable; downstream reasoning primarily uses compact Evidence Receipts.
- Observation, hypothesis, and recommendation are distinct data and presentation concepts.
- Evidence quantity is not evidence independence. Root sources, organizations, authors, repositories, and source types matter.
- Capabilities are framework-independent; technologies remain separately represented.
- Model calls sit behind replaceable interfaces. Tests use deterministic fakes or recorded fixtures and do not require paid APIs.
- User profile context is retrieved narrowly. Do not send a full profile, full corpus, or full conversation when a relevant slice suffices.
- Zero Riffs is a valid daily result. The system must not manufacture novelty.
- Only the user can approve `RIFF -> EXPLORATION` and `EXPLORATION -> PRD`.
- Coding-agent execution, autonomous PRs, complex frontend work, and every other PRD v0.1 non-goal remain out of scope.

## Goal order

| Goal | Outcome | Depends on |
|---|---|---|
| [G00](G00-foundation.md) | Executable application foundation | — |
| [G01](G01-provenance-store.md) | Provenance-first evidence store | G00 |
| [G02](G02-writing-ingestion.md) | Incremental ingestion framework and technical-writing source | G01 |
| [G03](G03-github-ingestion.md) | Incremental GitHub evidence | G02 |
| [G04](G04-job-ingestion.md) | Incremental job-market evidence | G02 |
| [G05](G05-evidence-receipts.md) | Versioned evidence compression and extraction | G02–G04 |
| [G06](G06-capability-model.md) | Reversible capability normalization | G05 |
| [G07](G07-user-capability-profile.md) | Evidence-backed personal capability model | G06 |
| [G08](G08-signal-engine.md) | Deterministic candidate generation and ranking | G06–G07 |
| [G09](G09-daily-riffs.md) | Deep arguments and zero-to-three daily Riffs | G08 |
| [G10](G10-decision-loop.md) | Investigation, lifecycle, and semantic decision memory | G09 |
| [G11](G11-explorations.md) | Human-approved bounded Explorations | G10 |
| [G12](G12-prds-and-agent-goals.md) | Learning PRDs and executable goal decomposition | G11 |
| [G13](G13-daily-operations.md) | Reliable scheduled end-to-end daily run | G09–G12 |
| [G14](G14-chatgpt-adapter.md) | Conversational ChatGPT-facing adapter | G10–G13 |
| [G15](G15-dogfood-release-gate.md) | Evaluated v0.1 dogfood release | G00–G14 |

G03 and G04 may be implemented in either order. All other goals should normally follow the table.

## PRD coverage

| PRD v0.1 concern | Owning goals |
|---|---|
| Three-source incremental evidence and deduplication | G01–G05 |
| Provenance from argument back to raw source | G01, G05, G09 |
| Capability/technology separation and normalization | G06 |
| Public, private, and generated capability evidence | G07 |
| Novelty, relevance, independence, and adversarial ranking | G08 |
| Zero-to-three complete daily arguments | G09 |
| Investigation, feedback, rejection, and resurfacing memory | G10 |
| Explicit human authority over both promotions | G10–G12 |
| Bounded collaborative Explorations | G11 |
| Learning PRDs and outcome-oriented executable goals | G12 |
| Token-efficient scheduled daily operation | G13 |
| Initial conversational ChatGPT experience | G14 |
| Extraction, normalization, signal, product, and dogfood evaluation | G05, G06, G08, G15 |
| Full Section 33 release acceptance | G15 |

## Canonical project scenarios

These short IDs keep goal handoffs tied to project-level outcomes without duplicating the PRD's full acceptance text.

- `SC-FOUNDATION-001` — A clean checkout can initialize, run, report health, and execute one worker cycle.
- `SC-EVIDENCE-001` — New evidence is incrementally stored once and remains traceable to its source and raw snapshot.
- `SC-CAPABILITY-001` — Different technologies can normalize to a capability without collapsing distinct capabilities.
- `SC-PROFILE-001` — Riff distinguishes public, private, hands-on, studied, and unknown capability evidence.
- `SC-SIGNAL-001` — Correlated or established volume is down-weighted while independent weak signals remain inspectable.
- `SC-RIFF-001` — A daily request returns zero to three provenance-backed arguments with counterarguments and personalization.
- `SC-DECISION-001` — User decisions persist semantically and affect later ranking/resurfacing.
- `SC-DELIVERY-001` — An explicitly approved Riff becomes a bounded Exploration, learning PRD, and agent-ready goals.
- `SC-DOGFOOD-001` — Dogfooding produces a user-reviewed investigation moment or stops broader development for signal improvement.

## Current handoff

G00, G01, G02, G03, and G04 are complete; G05 is ready. Every later goal remains queued behind its listed dependencies. A suitable Luna instruction for the next cycle is:

```text
Implement docs/goals/G05-evidence-receipts.md. Read the Riff PRD and docs/goals/README.md first, remain within G05 scope, follow its execution contract, verify every acceptance criterion, and return the completion report defined by the roadmap.
```

After a goal is accepted, update its status to `Complete` and change every newly unblocked goal from `Queued` to `Ready`. Use `In progress` only while an agent is actively implementing that goal.

## Definition of done for a goal

A goal is complete only when:

- its deliverables exist and are integrated rather than isolated demonstrations;
- every acceptance criterion is either verified or explicitly identified as pending human evaluation;
- tests cover the stated happy path and the material failure paths;
- migrations and interfaces are backward-compatible with completed goals, or the intentional break is documented;
- configuration, setup, and operator-facing behavior introduced by the goal are documented;
- no secrets, private evidence, paid-provider requirement, or live-network dependency is embedded in the test suite;
- the repository's full verification suite passes.

Passing tests alone is not proof of completion when the goal requires a user-visible or operator-visible behavior.

## Completion report contract

Each Luna run should finish with:

```text
Goal: Gxx — name
Status: complete | incomplete | blocked
Outcome delivered: ...
Key decisions: ...
Verification: command/result ...
Acceptance criteria: pass/fail list ...
Follow-ups: only work not required by this goal ...
```

The implementation agent must not mark G15 complete on the user's behalf: its qualitative dogfood criterion explicitly requires the user's judgment.
