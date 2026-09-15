# G24 connector verification — 2026-09-15

## Selected mechanism

Riff uses the provider-neutral bounded HTTP equivalent documented in
`docs/decisions/0010-provider-neutral-http-connector.md`:

- catalog: `GET /adapter/tools`
- calls: `POST /adapter/tools/{tool_name}`
- optional bearer auth: `RIFF_ADAPTER_TOKEN`
- loopback HTTP for local dogfooding; HTTPS and a restricted origin for deploys
- no automatic retries, bounded timeout, bounded response size

This is a replaceable connector contract. It does not encode the Perplexity
Computer opportunity context or any single job's requirements.

## Automated evidence

- `.venv/bin/python -m pytest -q -o addopts=''` → **98 passed, 88 skipped**
  (the skips are the opt-in Postgres tests, plus 2 warnings).
- `RIFF_DATABASE_URL=... .venv/bin/python -m pytest -m postgres -q -o addopts=''`
  → **88 passed, 98 deselected, 2 warnings**.
- `tests/test_connector.py` covers catalog/protocol validation, bearer auth,
  response limits, sanitized HTTP errors, invalid tool paths, no-retry calls,
  and a Postgres-backed read → decision → Exploration → selection → PRD
  approval → generation → export conversation.

## Live local proof

With Postgres already migrated and the daily fixture persisted:

```text
riff connector probe --url http://127.0.0.1:8010 --token <redacted>
→ protocol riff-tools-v1; 15 tools discovered

riff chat replay --file tests/fixtures/chat/tool-loop-v1.json --scenario daily \
  --url http://127.0.0.1:8010 --token <redacted>
→ SUCCEEDED; 1 tool call; 2 turns; daily_run_id c0e5101f-e379-486a-a6eb-c215ce00ecf3
```

The live API process was stopped after the check. No token was committed or
printed by the connector.

## External acceptance reconciliation

The provider-facing acceptance is complete through the native ChatGPT MCP
surface. The redacted transcript, persisted IDs, Inspector checks, and human
evaluation are recorded in `docs/reports/g24a-mcp-verification.md`:

- ChatGPT discovered the `/mcp` catalog and completed the persisted
  read → decision → Exploration → experiment → PRD → project/export workflow.
- Missing confirmation and stale-ID requests were rejected without mutation;
  repeated reads were stable and produced no duplicate writes.
- The user judged the interaction rough because UUIDs and implementation-style
  relay prompts were visible. That is a product-continuity follow-up in G32,
  not a failure of the connector's persistence, approval, or privacy boundary.

G24 is therefore complete. The provider-neutral HTTP contract remains the
replaceable boundary for other clients; provider-specific limitations must not
change Riff's persistence or approval invariants.

## Current-cycle regression (2026-09-15)

- `tests/test_connector.py tests/test_mcp_server.py` with the Docker Postgres
  URL → **11 passed**, 2 known dependency deprecation warnings.
- Full `pytest -m postgres -q -rA -o addopts=''` → **92 passed, 112
  deselected**, 2 known dependency deprecation warnings.
- Full `pytest -q -rA -o addopts=''` with Docker Postgres → **204 passed**, 2
  known dependency deprecation warnings.
- `git diff --check` → clean.
