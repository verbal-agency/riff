# G23 — Wire the ChatGPT tool-loop client

**Status:** Complete
**Depends on:** G14, G22
**Unlocks:** A real ChatGPT-compatible connector and end-to-end conversational acceptance
**PRD references:** Sections 4, 10, 15, 27–29, 32–33
**Canonical scenario:** `SC-CHATGPT-001`

## Outcome

An outer integration process can use Riff's existing `riff-tools-v1` adapter to
support a real conversational turn. It sends the user's request to a selected
model provider, translates the model's typed tool calls into calls to Riff,
returns bounded tool results to the model, and renders the final response.

Riff remains the system of record. The client stores no canonical Riff state,
does not fetch source providers directly, and does not put the full corpus or
profile into model context.

## User-visible proof

The user can ask for today's Riffs, request evidence for one Riff, search prior
Riffs, inspect a public capability slice, and receive a grounded conversational
answer containing source links and stable Riff identifiers.

## Scope

### 1. Provider-neutral model boundary

- Define a replaceable model-client interface for one supported ChatGPT/model
  API, with credentials supplied only through the process environment.
- Convert Riff's `TOOL_SCHEMAS` into complete model tool definitions with typed
  argument schemas, descriptions, and read-versus-mutate annotations.
- Keep provider-specific request/response formats behind the client boundary so
  the Riff adapter and domain repositories remain provider-neutral.

### 2. Bounded tool loop

- Implement the sequence: model request → zero or more validated tool calls →
  Riff adapter call → tool result → final model response.
- Enforce a maximum tool-call count, turn timeout, response-size bound, and
  explicit termination/error state.
- Return only the adapter's bounded result DTOs; never issue SQL or source
  requests from the integration client.
- Preserve tool-call and result correlation IDs for inspection without logging
  prompts, credentials, private profile text, or raw unrelated evidence.

### 3. Approval and failure boundaries

- Treat model-produced prose as insufficient for mutations. The client must
  surface the required user confirmation step and pass `USER_CONFIRMED` only
  when the user explicitly confirms in the integration flow.
- Surface unknown tools, invalid arguments, adapter errors, timeouts, and model
  refusal as typed, user-visible failures without retrying unsafe mutations.
- Make read retries bounded and idempotent; never replay a mutating call without
  an explicit retry decision.

### 4. Deterministic test harness and operator path

- Add a fake model client and scripted conversations for daily Riffs, evidence
  investigation, search, profile lookup, decision recording, and approval
  boundaries.
- Exercise the loop against the local FastAPI adapter with fixture-backed data;
  tests must not require a live model, network, database, or credential.
- Provide a local command or small runnable module that prints the tool trace
  and final response for a scripted conversation.
- Document environment variables, model selection, adapter URL, bounds, and
  troubleshooting.

## Non-goals

- Reimplementing Riff domain rules, retrieval, ranking, or approval logic in
  prompts or the client.
- Storing conversation history as canonical product state.
- Autonomous Exploration/PRD approval, job applications, source collection, or
  arbitrary tool execution.
- Committing provider credentials or requiring a paid model in automated tests.

## Acceptance criteria

- [x] The client discovers or loads the complete `riff-tools-v1` catalog and
  produces valid typed model tool definitions.
- [x] A scripted “What are today's Riffs?” turn makes the expected read tool
  call, returns its result to the model, and renders a grounded final response.
- [x] A scripted follow-up investigates a selected Riff and includes only the
  requested bounded evidence/provenance slice.
- [x] Unknown tools, malformed arguments, adapter failures, timeouts, and
  exhausted tool budgets produce deterministic typed errors.
- [x] Mutation attempts without explicit confirmation are rejected; approved
  decision/Exploration/PRD flows carry the required confirmation token and
  persist through the existing adapter only.
- [x] Fake-model tests cover the complete loop without live model/network
  dependencies, and the offline test suite remains green.
- [x] The local operator command and configuration are documented, including
  credential handling and redacted trace output.

## Handoff

The provider-neutral model protocol is `ModelClient.complete(messages, tools) ->
ModelResponse`; `model_tool_definitions` maps the complete `TOOL_SCHEMAS`
catalog to typed function parameters with mutation and confirmation
annotations. The default loop bounds are 8 turns, 12 calls, 30 seconds,
30,000 result characters, and 40,000 context/response characters. Fixture
replay proves daily, investigation, and confirmation-boundary turns without a
live model. G22 must still exercise the same loop against persisted Postgres
adapter state; G24 may add the provider-specific ChatGPT transport without
duplicating this orchestration.

## Current implementation slice (2026-09-14)

- `src/riff/chat_loop.py` provides provider-neutral model and tool-adapter
  protocols, typed tool definitions, bounded turns/calls/context/results/time,
  refusal and budget error codes, tool traces, safe adapter-error returns, and
  an explicit confirmation-provider boundary.
- `ScriptedModelClient` and `FixtureToolAdapter` support deterministic offline
  replay through `riff chat replay` using
  `tests/fixtures/chat/tool-loop-v1.json`.
- `tests/test_chat_loop.py` covers daily and investigation read calls, bounded
  results, unknown/invalid/adapter failures, refusal and timeout bounds,
  confirmation-token injection, and the CLI replay path.
- Offline verification: `.venv/bin/python -m pytest -q tests/test_chat_loop.py`
  (**11 passed**); the full offline suite also passes.
- Postgres verification exercises the same loop against a persisted
  `RiffToolAdapter` seeded by the daily fixture; the focused adapter suite and
  complete Postgres suite pass. G24 owns the actual ChatGPT connector and live
  end-to-end acceptance.

## Cycle verification

- `.venv/bin/python -m pytest -m postgres tests/test_adapter.py` — 3 passed.
- `RIFF_DATABASE_URL=postgresql://riff:riff-local-only@localhost:5432/riff
  .venv/bin/python -m pytest -m postgres` — 87 passed, 93 deselected, 2
  dependency warnings.
- `.venv/bin/python -m pytest -m 'not postgres'` — 93 passed, 87 deselected, 2
  dependency warnings.
- `.venv/bin/python -m riff chat replay --file
  tests/fixtures/chat/tool-loop-v1.json --scenario daily` — `SUCCEEDED`, one
  bounded tool call, two turns, and a grounded final response.
- No model credentials, network access, or provider-specific transport was
  introduced; those remain explicitly scoped to G24.
