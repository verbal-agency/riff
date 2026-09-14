# G09a — Make the daily Riff path locally executable

**Status:** Ready  
**Depends on:** G09  
**Unlocks:** G09b, G13  
**PRD references:** Sections 8, 9–10, 26–29, 33

## Outcome

An operator can run one deterministic, database-backed daily Riff generation
from a bounded local input fixture, inspect the persisted zero-to-three result,
and repeat the run without duplicate provider calls or records.

## User-visible proof

After starting local Postgres and applying migrations, one command generates a
daily result and a second identical command reports a cached/idempotent result.
The result is inspectable through `GET /riffs/daily/YYYY-MM-DD`.

## Scope

- Add a one-shot `riff daily generate` command and application service entry
  point that use `DailyRiffService` and the deterministic provider by default.
- Load a schema-versioned bounded input fixture containing ranked G08 candidate
  IDs, receipt/profile/decision slices, and candidate scores; preserve the same
  context limits and citation gate as the service API.
- Provide a database-backed local smoke setup that seeds only the evidence and
  receipt rows needed by the fixture, without live network or paid model calls.
- Return structured run counts, provider-call count, cache/idempotence state,
  and the daily-result URL.

## Non-goals

- Scheduling, retries across every upstream stage, external model credentials,
  ChatGPT formatting, Exploration/PRD creation, or production deployment.
- Replacing the G09 provider, repository, or publication policy.

## Acceptance criteria

- [ ] A clean local Postgres database can migrate, seed the bounded fixture, and
  generate a queryable daily result with zero, one, and three Riff cases.
- [ ] The command never publishes more than three Riffs and exposes an honest
  empty result when the fixture has no eligible candidate.
- [ ] An identical date/fixture/policy rerun performs zero additional provider
  calls and creates no duplicate daily run, Riff, context, or citation rows.
- [ ] Unknown, failed, or snapshot-only receipt IDs fail before publication and
  produce an actionable structured error.
- [ ] The command and API use the same persisted result; the API read path never
  invokes the provider.
- [ ] The smoke test is fixture-driven and requires no network, secrets, or paid
  services.

## Deliverables

- `riff daily generate` command and application entry point.
- Schema-versioned fixture under `tests/fixtures/riffs/` and deterministic seed
  helper.
- Focused tests in `tests/test_daily_smoke.py` plus API/cache assertions.
- README/runbook instructions for starting Postgres, migrating, generating, and
  querying a result.

## Execution contract

### Expected implementation surface

Extend `src/riff/riffs.py` or add `src/riff/daily.py` for the operator entry
point; extend `src/riff/cli.py`; add the fixture and `tests/test_daily_smoke.py`;
update `README.md` and `docs/architecture.md` with the local path. Reuse
migration `010_daily_riffs.sql`; do not add a second Riff schema.

### Canonical contract and behavior matrix

The fixture uses schema version `1` and contains `run_date`, `policy_version`,
and bounded candidate objects with `candidate_id`, `capability_id`, `score`,
`observation`, `receipt_ids`, `profile_slice`, and `decision_ids`. Invalid
fixture versions, missing fields, and out-of-bound lists fail before mutation.
The command returns `run_id`, `status`, `published_count`, `provider_calls`,
`cached`, and `result_url`.

| Condition | Required result |
|---|---|
| Three eligible candidates | Persist and return exactly three Riffs. |
| One eligible candidate | Persist and return one Riff. |
| No eligible candidates | Persist an `EMPTY` run with a non-fabricated reason. |
| Duplicate invocation | Return the existing run with `cached=true`; provider calls stay unchanged. |
| Invalid receipt | No Riff is published; structured error identifies the receipt. |

### Authority and side-effect boundaries

Only local Postgres state and the supplied fixture may be read or mutated. The
deterministic provider is the default; no network, credentials, subprocesses,
or external publication are allowed. Seed helpers must insert only fixture
evidence/receipt rows and must be safe to replay.

### Criterion-to-test map

| Criterion | Proof |
|---|---|
| End-to-end zero/one/three | `test_daily_smoke_zero_one_three` |
| Hard cap and honest empty | `test_daily_smoke_respects_cap_and_empty_reason` |
| Idempotence | `test_daily_smoke_duplicate_is_cached` |
| Citation failure | `test_daily_smoke_rejects_invalid_receipt` |
| Shared API result | `test_daily_smoke_result_matches_api` |

