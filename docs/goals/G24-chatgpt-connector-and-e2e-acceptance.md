# G24 — Connect ChatGPT and run the end-to-end conversation

**Status:** Queued
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
- [ ] The complete read-and-promote conversation succeeds against Postgres,
  with persisted IDs, provenance, and approval state verified afterward.
- [ ] No confirmation-free model sequence can create an Exploration or PRD,
  and no connector retry duplicates a mutation.
- [ ] Privacy, credential, transport, timeout, and error-boundary checks pass.
- [ ] Local setup and connector configuration are documented with safe
  placeholder credentials and readiness checks.
- [ ] Automated connector tests and the G22 Postgres regression suite pass;
  the user records a human evaluation of the conversational experience.

## Handoff

Report the selected integration mechanism, endpoint/auth configuration,
conversation evidence, persisted object IDs, automated results, and the user's
qualitative judgment. Any provider-specific limitation becomes a documented
follow-up rather than a change to Riff's product invariants.
