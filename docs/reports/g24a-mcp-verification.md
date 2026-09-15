# G24a MCP verification — 2026-09-14

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

## Acceptance status

The local MCP transport and offline contract are implemented. MCP Inspector
and ChatGPT Developer Mode require the operator's running process, reachable
Postgres, and (for ChatGPT) an external HTTPS URL, so the external transcript,
persisted end-to-end IDs, and qualitative evaluation remain pending until that
operator step is performed.
