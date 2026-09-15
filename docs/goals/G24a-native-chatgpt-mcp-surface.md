# G24a — Expose a native ChatGPT MCP surface and complete external acceptance

**Status:** Incomplete
**Depends on:** G22, G23
**Unlocks:** Native ChatGPT conversational dogfood of Riff
**PRD references:** Sections 4, 10, 15, 27, 32–33
**Canonical scenario:** `SC-CHATGPT-003`

**Implementation references:** [OpenAI MCP and Connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp) and [MCP server and UI quickstart](https://developers.openai.com/plugins/build/app-quickstart)

## Outcome

Riff exposes its existing conversational adapter through a standards-compliant
remote MCP server. A user can add the server to ChatGPT Developer Mode, inspect
the imported tools, and complete the read-and-promote conversation against the
same Postgres-backed Riff state. The MCP layer is a transport translation only:
Riff remains the system of record and continues to enforce privacy and approval
rules.

This goal closes the distinction between G24's provider-neutral HTTP test
connector and a native ChatGPT surface. It can reuse G24's adapter contract, but
does not require the provider-neutral connector to be complete. It does not encode any one job listing,
Perplexity Computer, or other opportunity as a product invariant.

## User-visible proof

From a new ChatGPT conversation, the user selects the Riff MCP app and asks for
today's Riffs, investigates one, records a reasoned decision, explicitly creates
an Exploration, selects an experiment, approves a PRD, and retrieves the
generated project. ChatGPT shows tool approvals and evidence links while all
durable IDs and lifecycle transitions come from Riff.

## Scope

### 1. MCP transport

- Add a Python MCP server using the official MCP SDK and Streamable HTTP at
  `/mcp`; support the protocol version and methods required by the current
  ChatGPT Developer Mode surface.
- Translate the existing `riff-tools-v1` catalog into MCP tool definitions
  without adding a second domain API or exposing Postgres.
- Return compact structured content plus text suitable for ChatGPT rendering;
  preserve stable IDs, source links, provenance, and uncertainty.
- Do not add a UI resource unless the text-only workflow demonstrates a concrete
  need; a web component is explicitly optional for this goal.

### 2. Tool and authority mapping

- Map read tools as read-only and mutating tools as state-changing in MCP
  annotations. Mark open-world behavior only where the underlying Riff tool
  actually reaches an external source.
- Preserve the outer user-confirmation boundary for `create_exploration`,
  `select_experiment`, `approve_prd`, and any later mutating promotion. A model
  argument or MCP text response cannot satisfy confirmation.
- Preserve G24's bounded timeout, response size, error sanitization, and no
  automatic mutation retry behavior.

### 3. Authentication and deployment

- Determine and document the current ChatGPT Developer Mode authentication
  contract (unauthenticated personal development, bearer, or OAuth) before
  exposing the endpoint beyond loopback. Do not silently treat a static token
  as production authentication if the surface requires OAuth.
- Keep local Postgres credentials and connector credentials in environment or a
  secret manager. Never log or commit them.
- Document loopback operation, an HTTPS tunnel or deployment URL ending in
  `/mcp`, health/readiness checks, origin/network restrictions, timeout policy,
  and credential rotation.

### 4. External acceptance

- Verify the endpoint with MCP Inspector using Streamable HTTP before attempting
  ChatGPT.
- Add the HTTPS `/mcp` URL in ChatGPT Developer Mode, refresh the connection
  after tool metadata changes, and capture a redacted transcript and MCP tool
  call trace.
- Exercise the complete read-and-promote workflow, a confirmation omission,
  stale ID, adapter failure, disconnect, repeated read, and one safe retry
  boundary in the ChatGPT surface.
- Record the user's judgment of usefulness, grounding, evidence visibility, and
  confirmation clarity separately from automated test results.

## Non-goals

- Replacing `RiffToolAdapter`, `ChatToolLoop`, or the existing application API.
- Building a ChatGPT UI widget, public marketplace listing, multi-tenant auth,
  or a general-purpose MCP gateway.
- Adding arbitrary browsing, autonomous approvals, source ingestion, job
  applications, or provider-specific product behavior.
- Treating a single opportunity, employer, or named platform as a universal
  recommendation rule.

## Acceptance criteria

- [ ] A Streamable HTTP MCP endpoint at `/mcp` passes MCP Inspector initialization,
  tool listing, and representative tool calls against a running Riff instance.
- [ ] ChatGPT Developer Mode can add the HTTPS `/mcp` URL, imports the documented
  Riff tools, and completes the read-and-promote conversation against Postgres.
- [ ] MCP tool schemas and annotations distinguish reads from mutations, expose
  stable IDs/provenance, and do not expose Postgres or unrelated private data.
- [ ] No confirmation-free sequence can create an Exploration or PRD, and a
  disconnect or retry cannot duplicate a mutation.
- [ ] Authentication, HTTPS/tunnel, origin restrictions, readiness, timeout,
  credential-redaction, stale-ID, malformed-call, and adapter-error checks pass.
- [ ] Offline MCP fixtures and Postgres tests cover positive, malformed,
  unsupported, privacy, confirmation, restart, repeated-read, and disconnect
  cases; the existing G22/G24 regression suites remain green.
- [ ] A redacted ChatGPT transcript, MCP trace, persisted IDs, configuration,
  and user qualitative evaluation are recorded.

## Execution contract

### Expected implementation surface

- `src/riff/mcp_server.py` (or an equivalent module named in the completion
  report) owns MCP server construction, transport setup, tool registration, and
  request-scoped configuration.
- `src/riff/connector.py` remains the provider-neutral HTTP test client; do not
  fork domain behavior into the MCP module.
- `tests/test_mcp_server.py` covers protocol handshake, catalog/schema mapping,
  annotations, auth, error bounds, confirmation, and duplicate-call behavior.
- `tests/fixtures/chat/mcp-e2e-v1.json` records tool metadata and a complete
  deterministic conversation; malformed and unsupported cases are separate
  fixture scenarios.
- Update `README.md`, `docs/architecture.md`, and add a decision record under
  `docs/decisions/` plus `docs/reports/g24a-mcp-verification.md`.

### Canonical contracts and invariants

- Domain calls continue through `RiffToolAdapter.call`; no MCP handler may write
  directly to Postgres or bypass repository validation.
- Tool names, required arguments, confirmation token semantics, durable IDs,
  provenance fields, and lifecycle statuses remain those of `riff-tools-v1`.
- MCP transport state (sessions, connection IDs, or caches) is disposable;
  canonical state is only the persisted Riff/Postgres state.
- Legal mutation transitions remain `USER_CONFIRMED` → application operation;
  model-supplied confirmation text is never sufficient.

### Deterministic behavior matrix

| Input/condition | Required result |
|---|---|
| Valid MCP initialize/list-tools | Protocol handshake and complete bounded catalog |
| Valid read call | Structured result with stable IDs and permitted evidence slice |
| Valid confirmed mutation | One durable application call and returned status/ID |
| Missing/invalid confirmation | Typed refusal; zero mutation calls |
| Unknown tool or malformed arguments | Typed MCP error; no database write |
| Stale ID or domain conflict | Sanitized error with no retry |
| Disconnect after mutation request | At-most-once connector request; replay is an explicit user action |
| Repeated read or server restart | Same persisted result; no duplicate records |
| Oversized response or timeout | Bounded typed error; no secret/body leakage |

### Authority and side-effect boundaries

- MCP may expose only the existing Riff adapter and its bounded results.
- Repository reads/writes remain inside Riff repositories and Postgres
  transactions; MCP has no SQL credentials or direct database access.
- Network access is limited to the MCP transport and explicitly configured
  adapter origin; no arbitrary URL fetching or subprocess execution.
- Credentials are process/environment inputs, never fixture contents or logs.
- ChatGPT/model calls remain outside Riff; the MCP server does not implement a
  model client or autonomous planner.
- External deployment/tunnel creation and ChatGPT Developer Mode configuration
  are operator actions recorded in the report, not automated side effects.

### Fixtures, replay, budgets, and proof map

- Positive fixture: initialize → list tools → daily read → investigate →
  decision → confirmed Exploration → selection → PRD approval → generation →
  export.
- Negative fixtures: missing confirmation, unknown tool, malformed arguments,
  stale ID, private-profile overfetch, unsupported protocol, timeout, oversized
  response, and disconnect after a mutation request.
- MCP sessions are disposable; a fixture replay must not depend on prior session
  IDs. Tool calls inherit G24's 8-turn/12-call/30-second conversational bounds.
- `tests/test_mcp_server.py` maps to criteria 1, 3, 4, and 5; the Postgres
  integration maps to criteria 2 and 6; the redacted transcript/report maps to
  criteria 2 and 7; MCP Inspector output maps to criterion 1.

## Cycle verification (2026-09-14)

The deadlock was removed by making G24a depend on the completed G22/G23 seams;
G24's provider-neutral connector remains a reusable contract, not a prerequisite
for the native transport. The implementation uses `mcp==1.30.0` with stateless
JSON Streamable HTTP. `riff api` now serves the existing FastAPI routes plus the
exact `/mcp` endpoint, and an explicit parent lifespan runs the SDK session
manager so mounted requests work under FastAPI.

Automated evidence:

```text
.venv/bin/python -m pytest -q tests/test_mcp_server.py -o addopts=''  → 5 passed
.venv/bin/python -m pytest -q -o addopts=''                            → 103 passed, 88 skipped
RIFF_DATABASE_URL=... riff migrate; pytest -m postgres -q             → passed
pytest -m postgres tests/test_adapter.py -q                          → 3 passed
uv lock --check; git diff --check; py_compile; riff --help            → passed
```

The focused tests cover bearer enforcement, preserved health routes,
initialize/list-tools, all 15 catalog entries, schema and read/mutation
annotations, structured adapter dispatch, missing-confirmation refusal, and
unknown-tool errors. `tests/fixtures/chat/mcp-e2e-v1.json` records the positive
workflow and negative replay cases. README, architecture, decision 0011, and
the operator report document Inspector and ChatGPT Developer Mode setup.

### Criterion status

- **Pass (local transport):** official MCP SDK Streamable HTTP at `/mcp`
  initializes and lists the complete bounded catalog in tests.
- **Pass (local mapping):** typed schemas, structured results, stable adapter
  IDs/provenance, and read/mutation annotations are verified without exposing
  Postgres.
- **Pass (local safety):** missing confirmation is rejected before adapter
  dispatch; unknown/malformed calls return typed MCP errors; repeated reads do
  not create state; bearer auth and SDK host checks remain enabled.
- **Pass (documentation/configuration):** local command, token handling,
  readiness, HTTPS/tunnel, Inspector, and ChatGPT Developer Mode steps are
  recorded without secrets.
- **Pass (running local service):** Docker Postgres was healthy; migrations had
  no pending work; the real `riff api` process returned MCP `initialize` 200
  with bearer auth and `/health/live` 200.
- **Pending operator acceptance:** MCP Inspector against a running process and
  the external ChatGPT Developer Mode read-and-promote transcript require the
  operator's reachable Postgres and HTTPS/tunnel session. The persisted IDs and
  qualitative usefulness/grounding/confirmation evaluation therefore remain
  unrecorded in this cycle.

## Handoff

Report the MCP SDK/version and transport, endpoint/auth configuration, Inspector
results, ChatGPT Developer Mode transcript and tool trace, persisted IDs, test
commands, privacy review, and the user's qualitative judgment. Any provider
rollout or authentication limitation becomes a documented follow-up rather than
a change to Riff's product invariants.
