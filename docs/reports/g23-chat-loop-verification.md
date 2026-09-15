# G23 tool-loop verification — 2026-09-14

## Result

`PASS` for the provider-neutral tool-loop client and persisted adapter exercise.

## Verification

| Check | Result |
|---|---|
| Persisted adapter-focused tests | `3 passed, 2 warnings` |
| Complete Postgres-marked suite | `87 passed, 93 deselected, 2 warnings` |
| Offline suite | `93 passed, 87 deselected, 2 warnings` |
| CLI fixture replay | `SUCCEEDED`, 1 tool call, 2 turns |

The persisted test seeds the daily Riff fixture in Postgres, runs the real
`ChatToolLoop` with `RiffToolAdapter`, and verifies the bounded daily result and
trace correlation. The CLI replay remains fixture-only and requires no database,
credentials, network, or live model.

The two warnings are existing FastAPI/Starlette/httpx and AnyIO dependency
deprecations. Provider-specific ChatGPT transport remains scoped to G24.
