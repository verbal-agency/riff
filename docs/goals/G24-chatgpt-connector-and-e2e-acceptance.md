# G24 — Connect ChatGPT and run the end-to-end conversation

**Status:** Incomplete
**Depends on:** G22, G23
**Unlocks:** User-facing conversational dogfood of Riff
**PRD references:** Sections 4, 10, 15, 27, 32–33
**Canonical scenario:** `SC-CHATGPT-002`

## Outcome

A supported ChatGPT-compatible integration can connect to a running Riff
service, discover its tools, and complete the initial conversational workflow
against real Postgres-backed state. The connection is authenticated and
bounded, while Riff's approval and privacy rules remain enforced below the
model.

## User-visible proof

From ChatGPT, the user can ask what is new, inspect a Riff's evidence and
counterevidence, record a reasoned decision, explicitly create an Exploration,
select an experiment, approve a PRD, and retrieve the generated project—without
the connector becoming the system of record.

## Scope

### 1. Supported connector surface

- Select the currently supported ChatGPT integration mechanism (MCP,
  connector, or equivalent) during implementation and document the decision.
- Expose the existing adapter through the required transport without exposing
  Postgres directly or adding a second domain API.
- Publish tool names, descriptions, argument schemas, read/mutate semantics,
  source-link behavior, and explicit confirmation requirements.

### 2. Local and deployable configuration

- Provide a documented local setup that starts Riff, points the connector at
  the adapter, and uses the G22-verified database configuration.
- Define the minimum production-like requirements for HTTPS, authentication,
  origin/network restrictions, timeouts, and secret rotation; keep secrets out
  of the repository and logs.
- Make connector and adapter health/readiness failures clear and recoverable.

### 3. End-to-end acceptance

- Run a scripted conversation covering daily Riffs, investigation, search or
  profile lookup, a rejection/decision, Exploration creation, experiment
  selection, PRD approval, and project export.
- Verify every read is backed by persisted Riff state and every mutation returns
  a durable identifier/status from Riff.
- Verify a restart of the connector loses no canonical state and a repeated read
  does not create duplicate records.
- Verify private profile data, unrelated evidence, credentials, and raw prompts
  are not leaked through tool results or logs.
- Exercise connector disconnects, adapter errors, stale IDs, and confirmation
  omissions; no unsafe mutation may be retried automatically.

### 4. Human evaluation packet

- Capture the exact connector configuration, conversation transcript or
  redacted trace, Postgres run IDs, tool calls, and final rendered responses.
- Ask the user to judge usefulness, grounding, evidence visibility, and whether
  confirmation boundaries feel clear; record the result separately from
  automated tests.

## Non-goals

- Replacing the Riff API/adapter, adding broad assistant memory, or moving
  canonical state into ChatGPT.
- Autonomous approvals, source ingestion, job applications, or arbitrary
  browsing/tool execution.
- A public multi-tenant service or team/authentication model beyond the minimum
  connector boundary required for this single-user deployment.

## Acceptance criteria

- [ ] A supported ChatGPT-compatible connector successfully discovers and calls
  the documented Riff tools against a running instance.
- [x] The complete read-and-promote conversation succeeds against Postgres,
  with persisted IDs, provenance, and approval state verified afterward.
- [x] No confirmation-free model sequence can create an Exploration or PRD,
  and no connector retry duplicates a mutation.
- [x] Privacy, credential, transport, timeout, and error-boundary checks pass.
- [x] Local setup and connector configuration are documented with safe
  placeholder credentials and readiness checks.
- [ ] Automated connector tests and the G22 Postgres regression suite pass;
  the user records a human evaluation of the conversational experience.

## Handoff

Report the selected integration mechanism, endpoint/auth configuration,
conversation evidence, persisted object IDs, automated results, and the user's
qualitative judgment. Any provider-specific limitation becomes a documented
follow-up rather than a change to Riff's product invariants.

## Cycle verification (2026-09-14)

The provider-neutral equivalent selected for the transport slice is bounded
HTTP over the existing `riff-tools-v1` adapter
(`docs/decisions/0010-provider-neutral-http-connector.md`). `riff connector
probe` discovers the catalog, and `riff chat replay --url` runs the existing
deterministic model fixture against a live API. `RIFF_ADAPTER_TOKEN` enables
optional bearer enforcement; loopback HTTP is documented as local-only.

Automated connector tests cover catalog validation, auth headers, response
limits, sanitized HTTP errors, invalid tool paths, and the no-retry mutation
boundary. The remaining G24 acceptance is external: run the documented replay
against the G22 Postgres instance, then connect the currently supported ChatGPT
surface and record the human usefulness/grounding/confirmation evaluation.

### Criterion status

- **Pass (Riff-side equivalent):** the authenticated HTTP connector discovered
  all `riff-tools-v1` tools and a live daily replay returned the persisted
  `daily_run_id` from Postgres.
- **Pass:** the focused Postgres connector test completed read → decision →
  Exploration → experiment selection → PRD approval → generation → export,
  then re-read the project without creating a duplicate.
- **Pass:** confirmation-free promotion remains rejected by the existing loop;
  the HTTP connector performs no automatic retries, and the test suite verifies
  one request per call.
- **Pass:** connector auth, credential-safe URL validation, response bounds,
  timeout/error codes, path validation, and private-profile omission are
  covered by `tests/test_connector.py`.
- **Pass:** local setup, safe placeholder token configuration, readiness probe,
  HTTPS/restricted-origin requirements, and rotation guidance are documented
  in `README.md` and `docs/decisions/0010-provider-neutral-http-connector.md`.
- **Pending external evaluation:** a provider's current ChatGPT connector must
  be pointed at the documented boundary, and the user must record the human
  usefulness/grounding/confirmation judgment. This is intentionally not
  replaced with a Perplexity-specific implementation or a job-specific rule.
