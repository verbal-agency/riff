# Decision 0010 — Use a bounded provider-neutral HTTP connector for G24

## Context

G14 and G23 already provide the Riff tool catalog and a provider-neutral model
tool loop, but no transport client had been exercised against a running Riff
instance. G24 needs a connector boundary that can be used by a supported
ChatGPT-compatible surface without moving canonical state or product rules out
of Riff.

## Decision

G24 ships `HttpToolAdapter`, a small HTTP client for the existing
`riff-tools-v1` endpoints. It discovers tools with `GET /adapter/tools` and
calls them with `POST /adapter/tools/{tool_name}`. The client uses bounded
timeouts and response sizes, refuses credentials in the URL, sends an optional
environment-provided bearer token, and never retries requests. The API
optionally enforces the same bearer token when `RIFF_ADAPTER_TOKEN` is set.

Loopback HTTP is supported for local dogfooding. A deployed connector must use
HTTPS, a private/restricted origin, and a secret manager or equivalent process
environment; the token is never printed or persisted. The transport is an
equivalent ChatGPT-compatible contract, not a vendor-specific ChatGPT or
Perplexity implementation. Provider-specific setup remains a human-evaluation
follow-up and cannot change Riff's approval, privacy, or persistence rules.

## Consequences

- `riff chat replay --url ...` can exercise the existing scripted conversation
  against a live adapter and Postgres without a paid model credential.
- `riff connector probe --url ...` gives operators a bounded readiness/catalog
  check.
- HTTP errors are intentionally summarized rather than copying response bodies
  into model traces, reducing credential and private-evidence leakage.
- A future MCP or provider SDK can implement the same `ToolAdapter` protocol
  without changing domain endpoints.
