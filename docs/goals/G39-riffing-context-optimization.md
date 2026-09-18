# G39 — Optimize conversational riffing context

**Status:** Complete
**Depends on:** G23, G24a, G32, G36, G37, G38
**Unlocks:** Longer, more useful riffing without loading the entire evidence base
**Canonical scenario:** `SC-RIFF-CONTEXT-001`

## Outcome

Riff gives the operator a compact, relevant context packet for conversational
riffing. It retrieves only the evidence, project/goal, profile, opportunity,
decision, and prior-turn slices needed for the current question, while making
the omitted evidence and uncertainty inspectable. The operator can ask for more
evidence naturally without UUID relay or a context reset.

## Scope

- Define a deterministic context-packet contract with source diversity,
  relevance, freshness, project/goal fit, and uncertainty fields.
- Retrieve bounded Evidence Receipts rather than raw papers, code, incident
  reports, or full repository bodies; preserve links for explicit drill-down.
- Enforce configurable per-request limits for source count, characters/tokens,
  tool calls, turns, and total context. Keep current G32 safety bounds as the
  default ceiling.
- Deduplicate repeated receipts across turns, retain one canonical citation,
  and expose an explicit “more evidence” path that expands the packet in a
  controlled way.
- Add model usage telemetry when the provider supplies it, plus deterministic
  estimates when it does not. Report input/output/context usage without
  persisting raw prompts or unrestricted conversation history.
- Compare goal-aware context with the existing profile-only/broad retrieval
  baseline on relevance, actionability, distinctiveness, uncertainty honesty,
  and token consumption.

## Non-goals

- Increasing context limits until the model accepts the full corpus.
- Persisting every turn as durable memory, automatic preference learning, or
  hidden summarization that cannot be audited.
- Replacing evidence ranking, project-goal extraction, or source provenance
  with embeddings alone.

## Acceptance criteria

- [x] A fixture-backed context packet selects a bounded, diverse set of receipts
  for an incident-engineering and a Paper2Tool-style question, with project and
  goal citations where relevant.
- [x] The packet remains below configured character/token budgets and reports
  what was omitted, why it was selected, and what uncertainty remains.
- [x] Repeated turns do not duplicate the same receipts; an explicit follow-up
  can request more evidence without exceeding the global turn/call budget.
- [x] Raw source bodies remain outside normal model context, and redaction keeps
  credentials, private evidence, stable IDs, and unrestricted history out of
  ordinary model-facing text.
- [x] Provider usage telemetry and deterministic fallback estimates are
  recorded in the bounded trace; no raw prompt persistence is introduced.
- [x] Offline, connector, and Postgres tests cover restart, compaction,
  ambiguity, stale evidence, synthetic evidence, budget exhaustion, and
  confirmation boundaries.
- [x] A scripted and human comparison records whether the optimized packet is
  more useful than the baseline at lower or equal token cost; failures route to
  a concrete retrieval or rendering follow-up.

## Verification note

The bounded packet, source diversity/correlation policy, character/token
estimates, redaction, more-evidence paging, adapter/MCP/CLI surfaces, provider
usage capture, deterministic fallback estimates, and Postgres cleanup path are
covered by automated tests. The scripted comparison is represented by the
fixture-backed selection and usage assertions. A connected human usefulness
comparison remains explicitly pending and is routed to `BL-G39-001`; no
usefulness claim is inferred from protocol success.

Verification run: `141 passed, 107 deselected` (offline suite), plus the
focused G39 Postgres repository test passed against the local Docker database.

## Execution contract

G39 changes retrieval/rendering and measurement, not the source ledger. Keep
the operator's conversational riffing as the place where curriculum and
execution meaning are developed. Any new durable preference or evidence
selection policy must be versioned and explicitly inspectable.
