# Decision 0011 — Expose Riff through the official MCP Streamable HTTP transport

## Context

G24 proved a provider-neutral HTTP connector, but native ChatGPT Developer Mode
expects an MCP server URL rather than Riff's compact REST catalog. We need a
standards-compliant transport without moving domain logic or persistence into a
provider integration.

## Decision

Use the official Python `mcp` SDK (version `1.30.0` in this repository) with
stateless Streamable HTTP at `/mcp`. `src/riff/mcp_server.py` registers typed
wrappers for the complete `riff-tools-v1` catalog, returns SDK structured
content, and marks read/mutation semantics with MCP annotations. The normal
`riff api` process mounts the MCP app, while all calls still dispatch through
`RiffToolAdapter`.

The optional `RIFF_ADAPTER_TOKEN` protects `/mcp` with bearer authentication;
the SDK's DNS-rebinding protection remains enabled. Local defaults allow only
loopback hosts/origins. A deployed operator must set the explicit,
comma-separated `RIFF_MCP_ALLOWED_HOSTS` and `RIFF_MCP_ALLOWED_ORIGINS` values
for the HTTPS host and calling origin. Production use requires HTTPS and a
restricted origin or tunnel. Static bearer auth is a local/development seam,
not a claim of ChatGPT OAuth support.

## Consequences

- MCP Inspector and ChatGPT can use one stable `/mcp` URL and the same durable
  Riff IDs, provenance, privacy filters, and approval checks as the REST loop.
- MCP sessions are disposable and never become a second system of record.
- The current adapter's literal `USER_CONFIRMED` contract remains visible on
  promotion tools; external ChatGPT approval/transcript evidence is an operator
  acceptance step rather than an autonomous server behavior.
- OAuth, multi-tenant deployment, and ChatGPT-specific approval metadata remain
  follow-up work if the external surface requires them.
