# G24a MCP verification — 2026-09-15

## Local implementation

- Python MCP SDK: `mcp==1.30.0`.
- Transport: stateless Streamable HTTP, exact endpoint `/mcp`, JSON responses.
- Host/origin protection: SDK DNS-rebinding checks plus optional
  `RIFF_ADAPTER_TOKEN` bearer middleware scoped to `/mcp`; deployment allowlists
  are configured with `RIFF_MCP_ALLOWED_HOSTS` and `RIFF_MCP_ALLOWED_ORIGINS`.
- Tool catalog: all 15 `riff-tools-v1` operations, with typed input schemas,
  structured output, and read/mutation annotations.

## Automated evidence

`tests/test_mcp_server.py` verifies bearer enforcement, parent API health,
initialize/list-tools, complete catalog/schema mapping, annotations, structured
read calls, missing-confirmation refusal, confirmed adapter dispatch, and
unknown-tool errors without a database or network.

With Docker Postgres healthy, `riff migrate` reported no pending migrations and
the full Postgres-marked suite completed successfully. A real local API smoke
run also returned MCP `initialize` 200 from
`http://127.0.0.1:8765/mcp` with the bearer token and `/health/live` returned
`{"status":"ok","service":"riff"}`.

The focused persisted adapter check is independently reproducible:
`tests/test_adapter.py` → **3 passed** against the Docker Postgres database.

The protocol fixture is `tests/fixtures/chat/mcp-e2e-v1.json`; it records the
positive read-and-promote sequence and separate malformed, stale, repeat, and
disconnect cases for external replay.

## Operator verification

```sh
export RIFF_ADAPTER_TOKEN=local-mcp-only
uv run riff migrate
uv run riff api --host 127.0.0.1 --port 8000
npx @modelcontextprotocol/inspector@latest
```

Select Streamable HTTP and enter `http://127.0.0.1:8000/mcp` in Inspector.
For ChatGPT Developer Mode, publish an HTTPS URL ending in `/mcp`, add it as an
MCP app, refresh after metadata changes, and record a redacted transcript and
tool trace. Do not put tokens in fixtures or logs.

## External ChatGPT acceptance (2026-09-15)

The configured HTTPS tunnel and running API were reachable from ChatGPT
Developer Mode. A read-only request returned the persisted daily run for
`2026-09-15` and the top Riff
`00ab48b5-1fb0-51ff-8404-4dba8d7f7cd3`, including fixture provenance,
confidence, supporting receipt, and absence of counterevidence.

The redacted positive-path transcript then completed:

1. Missing-confirmation `create_exploration` was rejected with a required
   `confirmation_token` validation error and no write.
2. Decision `e2a3e482-f1d6-44b2-8b12-56f07ad6453e` recorded
   `APPROVE_EXPLORATION` with evidence snapshot `daily-r1`.
3. Confirmed Exploration `e02ac03f-7af8-45b9-b872-f153662c4678` was created
   as `DRAFT`.
4. Experiment
   `e02ac03f-7af8-45b9-b872-f153662c4678-exp-1` was selected; the Exploration
   advanced to version 2 and `SELECTED`.
5. PRD approval `cfeb16d4-ef74-4240-9f44-51c4c0a17d8c` was recorded.
6. Project `ce2d59b5-864f-48fd-be26-ee286be3014a` was generated as `READY`,
   version 1, with three goals.
7. `get_project` and `export_project` returned the same project ID and stable
   Markdown; no duplicate writes occurred.

Read-only negative checks also passed: a repeated `get_project` returned
identical payloads, and stale Riff ID
`00000000-0000-0000-0000-000000000000` returned `Riff not found` without retry
or mutation. The database contains one decision, one Exploration, one PRD
approval, one project, and three project goals for this acceptance run.

## MCP Inspector verification (2026-09-15)

MCP Inspector CLI was run against the same HTTPS `/mcp` tunnel with bearer
authentication and no mutating tool invocation:

```text
inspector-cli --cli --transport http --method initialize  -> success
inspector-cli --cli --transport http --method tools/list   -> success
```

Inspector reported server `Riff` version `1.30.0`, negotiated protocol
`2025-11-25`, and returned all 15 `riff-tools-v1` tools. The returned schemas
included required `confirmation_token` fields for mutating operations and
read/mutation annotations for every tool.

## Human evaluation (2026-09-15)

The user completed the workflow but judged the experience rough. The main
friction was not yet attributable to transport versus product behavior because
the operator had to relay implementation-oriented prompts and manually carry
UUIDs between turns. The desired experience is a natural conversation that
starts from a concept, keeps the relevant Riff/Exploration context implicitly,
supports iterative refinement, and only asks for a PRD when the user requests
one. Raw UUIDs should remain audit details rather than conversational handles.

This evaluation is accepted as evidence that the native surface works, while
the interaction-quality gap is routed to follow-up goal G32.

## Acceptance status

The local MCP transport, Postgres-backed workflow, MCP Inspector checks,
ChatGPT Developer Mode read-and-promote transcript, and human evaluation are
verified. G24a is complete as a transport and lifecycle acceptance goal; the
natural-language continuity and UUID-free interaction improvements are tracked
in G32. The transcript deliberately omits tokens and unrelated profile data.
