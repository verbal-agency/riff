# G42 provider verification — 2026-10-26

Operator setup and connected-surface troubleshooting are consolidated in `docs/operator-runbook.md`.

## Automated result

The G42 acceptance suite completed successfully against the configured local
Postgres database:

```text
.venv/bin/python -m pytest -q -o addopts='' \
  tests/test_reasoning.py tests/test_g42_reasoning.py \
  tests/test_connector.py tests/test_operations.py
→ 32 passed, 2 warnings in 23.20s
```

The suite covers provider selection, recorded responses, bounded calls and
cache reuse, token/cost limits, invalid provider output, Postgres live-shaped
telemetry, connector protocol/auth/response bounds, persisted read-to-project
workflow behavior, leases, readiness, recovery, and canonical report
redaction.

The local environment contains a provider key, but no additional paid call was
made in this cycle. The previously recorded 2026-10-11 smoke remains the
bounded real-provider evidence: one `gpt-4o-mini` call accepted the compact
context and returned a publication-shaped structured draft with the expected
receipt citation. A worker replay with evidence below the publication gate
correctly returned `VALID_EMPTY` without calling the provider.

## Remaining human acceptance

G42 remains **In progress** because one criterion requires a connected
ChatGPT/MCP operator check. With the local API and HTTPS `/mcp` tunnel running,
the operator should ask the connected Riff surface to retrieve the recorded
smoke result or run the one-call command from `README.md`, then verify:

1. the answer cites only the supplied receipts;
2. uncertainty, counterevidence, and insufficient-evidence states are visible;
3. no raw prompt, credential, or unrestricted source body is exposed; and
4. the interaction is understandable without manually carrying UUIDs.

Record the redacted transcript and outcome in this report. If the interaction
fails, route the concrete defect to G32/G45 rather than relaxing G42's
provenance or budget gates.

## Operator command

```sh
set -a; source .env; set +a
RIFF_REASONING_PROVIDER=openai RIFF_REASONING_MODEL=gpt-4o-mini \
RIFF_REASONING_MAX_CALLS=1 \
uv run riff worker --replay-live --limit 20 --date 2026-10-11 \
  --policy-version riff-g42-openai-smoke-v1 --resume
```

This command is intentionally bounded to one model call. It must be run only
when the operator explicitly wants to incur the provider cost.
