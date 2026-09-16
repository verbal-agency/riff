# G32 — Make conversational Riff exploration natural and context-preserving

**Status:** Complete
**Depends on:** G10, G11, G12, G23, G24a
**Unlocks:** Low-friction concept-to-PRD dogfooding
**PRD references:** Sections 4, 10, 15, 18, 27, 32–33
**Canonical scenario:** `SC-CHATGPT-004`

## Outcome

Riff supports a natural conversation that begins with a concept or daily Riff,
keeps the relevant context across turns, and lets the user investigate,
combine, narrow, or extend the idea until it is worth a PRD. Internal UUIDs and
tool names remain available for auditability but are not required as user-facing
handles. The user explicitly asks for a PRD when ready; Riff does not force
premature lifecycle transitions.

## User-visible proof

The user can ask what a concept means, ask follow-up questions such as “how
could this fit the project we just discussed?”, request another angle, and
compare variants without copying IDs. Riff resolves references from bounded
conversation context, asks a concise disambiguating question when needed, and
shows a clear natural-language confirmation before durable mutations. A final
“turn this into a PRD” request creates the same approved Exploration/PRD state
as the existing adapter flow.

## Scope

### 1. Conversational handles and context

- Add ephemeral, session-scoped handles for Riffs, evidence groups,
  Explorations, experiments, and projects (for example, “the top Riff” or
  “the public artifact experiment”).
- Resolve handles against a bounded recent tool-result/context window and stable
  persisted IDs; never guess across multiple plausible matches.
- Keep canonical state in Riff/Postgres. Session context is disposable and may
  be reconstructed from explicit IDs after restart.
- Render raw UUIDs only in an expandable audit/detail field or when the user
  asks for them.

### 2. Natural-language progression

- Support concept explanation, evidence inspection, follow-up questions,
  candidate transformations, comparison, and “ready for PRD” intent without
  requiring tool vocabulary.
- When the user rejects a current Riff, provide bounded alternatives without
  repeating it, and let the user map any selected Riff to a concrete workflow
  scenario as a read-only fit assessment.
- Preserve parent/child lineage and the assumptions changed by each refinement.
- Keep Exploration creation, experiment selection, PRD approval, and other
  mutations behind the existing explicit confirmation boundaries.
- Ask for clarification when a reference is ambiguous, stale, or outside the
  bounded context; do not silently select an ID.

### 3. Presentation and bounded model context

- Add a user-facing response renderer that summarizes results compactly while
  retaining citations, uncertainty, and source links.
- Send only the relevant Riff/project/profile slices to the model; do not turn
  the conversation into canonical memory or expose unrelated private evidence.
- Make lifecycle state and the next available action clear without exposing
  implementation-oriented prompts or raw tool payloads.
- Treat a missing current-day run as a valid no-result state: explain the gap,
  offer the latest persisted result as clearly dated context when available,
  and never fabricate a current-day Riff.

### 4. Evaluation and regression coverage

- Add scripted conversations for concept → investigation → refinement →
  comparison → PRD request, plus restart, ambiguity, stale-reference,
  correction, and confirmation omission cases.
- Measure turn success without copied IDs, clarification rate, accidental
  mutation rate, citation/uncertainty coverage, context-window bounds, and
  user-rated usefulness and friction.
- Compare the natural-language flow with the G24a relay-style baseline and
  record the user's qualitative judgment separately from protocol correctness.

## Non-goals

- Moving canonical state or approvals into ChatGPT conversation memory.
- Removing stable IDs from audit logs, APIs, or persisted provenance.
- Autonomous Exploration/PRD creation, repository changes, or automatic
  interpretation of an ambiguous reference.
- Building a general assistant memory system or broad unbounded context window.

## Acceptance criteria

- [x] A user can start from a persisted Riff and complete at least two rounds of
  follow-up/refinement without supplying a UUID or tool name.
- [x] The assistant presents concise natural-language summaries with citations,
  uncertainty, and no unrelated private/profile data.
- [x] A reference with one clear match resolves correctly; an ambiguous or
  stale reference produces clarification or a bounded error without mutation.
- [x] The user can explicitly request a PRD after the conversation has matured,
  and the existing confirmation/approval contracts remain enforced.
- [x] Session restart or context compaction preserves canonical state and
  allows explicit-handle recovery without duplicate writes.
- [x] Offline, Postgres, and ChatGPT-surface tests cover the positive flow,
  correction, ambiguity, stale IDs, privacy, confirmation, and restart cases.
- [x] A missing requested daily date returns a bounded no-result explanation
  with the latest dated context when available, without creating a run.
- [x] A rejected/current Riff can yield bounded alternatives, and a Riff can
  be mapped to a concrete scenario without creating durable lifecycle state.
- [x] Human evaluation shows lower friction and less UUID/tool relaying than
  the G24a baseline, or records the remaining gap and routes a follow-up.

## Handoff

Report the handle/context contract, intent and disambiguation behavior,
renderer examples, bounded-context policy, comparison metrics, transcript
evidence, and the user's qualitative judgment. Any request for persistent
assistant memory or autonomous actions becomes a separately scoped goal.

## Implementation verification (2026-09-15)

- `ConversationContext` binds bounded session labels to canonical IDs and
  rejects ambiguous or stale natural-language references without a tool call.
- `ConversationSession` carries message history across turns while keeping the
  session context disposable; explicit persisted IDs can rebind after restart.
- `NaturalLanguageRenderer` removes IDs, token-like fields, and private-profile
  payloads from model context while preserving citations, uncertainty, and the
  full bounded audit trace.
- Missing daily dates now return a dated latest-result summary without UUIDs or
  fabricated rank claims; bounded references such as “the top Riff” resolve to
  the newest published result for follow-up inspection.
- Offline scripted coverage is in `tests/test_chat_loop.py`; the existing
  Postgres adapter-flow tests continue to verify canonical state, restart, and
  approval persistence. Native MCP instructions now carry the same handle and
  disambiguation policy.
- Human evaluation is complete: the user confirmed the updated flow is an
  improvement, found follow-ups solid, and validated bounded alternate
  recommendations plus scenario mapping as the remaining interaction needs.
