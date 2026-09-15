# G33 — Observe the user's GitHub account with explicit scope

**Status:** Ready
**Depends on:** G03, G22, G24a, G26
**Unlocks:** Account-aware project selection and source monitoring
**PRD references:** Sections 4, 7.2, 8, 21–22, 27, 33
**Canonical scenario:** `SC-GITHUB-ACCOUNT-001`

## Outcome

Riff can observe a user-authorized GitHub account at a declared scope, retain
stable account and repository identity, and offer the user an explicit set of
owned public repositories to add to the G26 project inventory. Account
observation is provenance-bearing and privacy-bounded; it does not infer that
the user is proficient in every repository or import private code by default.

## User-visible proof

The user can connect or configure a GitHub account, ask ChatGPT which of their
repositories are available, select a repository in natural language, and have
it onboarded into the G26 project inventory without copying provider IDs.
The user can inspect the observed account scope, last refresh, omitted fields,
and revoke or narrow the scope.

## Scope

### 1. Account identity and scope

- Add a durable account-observation record keyed by GitHub provider account ID,
  with username, provider, consent timestamp, scope version, status, and last
  successful observation.
- Support a public-metadata baseline: account identity, owned public
  repositories, stable repository IDs, names, visibility, archive/fork flags,
  and timestamps. Public contribution/activity events are opt-in and bounded.
- Keep credentials process-only or secret-manager-backed; never persist tokens,
  authorization headers, private code, or raw account responses.
- Make disable/revoke and scope narrowing append-only, auditable transitions.

### 2. Repository selection and G26 integration

- Normalize account repositories to the existing G03 identity contract and
  present deterministic selection candidates with rename/transfer aliases.
- Let the user explicitly add selected repositories to the G26 inventory;
  selection must not silently onboard every repository.
- Preserve account-observation provenance on the inventory decision while
  keeping project snapshots and capability assessments separate.
- Clearly label missing, private, inaccessible, and out-of-scope repositories
  as unknown/omitted rather than treating absence as evidence.

### 3. ChatGPT and operator surfaces

- Add bounded read operations for account status and available repositories,
  plus a confirmation-gated operation to onboard a selected repository.
- Resolve natural-language repository names only when unambiguous; expose the
  stable provider ID in audit details, not as a required conversational handle.
- Provide terminal commands for connect/status/list/select/revoke so the same
  boundary works without ChatGPT.

## Non-goals

- Private repository content, code cloning, code execution, commit mutation,
  issue writes, OAuth UI, or background account surveillance without consent.
- Treating commit counts, stars, repository ownership, or language metadata as
  proof of personal capability.
- Replacing G03 collection or G26 project snapshots.

## Acceptance criteria

- [ ] A user-authorized account observation persists stable account identity,
  scope, consent, status, and last-success metadata without storing a token.
- [ ] A bounded fixture lists owned public repositories with stable provider IDs,
  visibility, rename aliases, and explicit omitted/unknown cases.
- [ ] The user can explicitly select one repository for G26 onboarding; an
  unselected repository is not added to the project inventory.
- [ ] Revocation or scope narrowing prevents subsequent collection and retains
  an auditable prior observation without deleting historical evidence.
- [ ] Account observations and repository selections remain distinct from user
  capability/profile claims and generated Riff projects.
- [ ] ChatGPT and terminal surfaces expose bounded account/repository results,
  require confirmation for onboarding, and resolve ambiguous names safely.
- [ ] Offline, Postgres, and scripted conversational tests cover consent,
  token redaction, pagination/replay, duplicate/rename handling, private and
  inaccessible repositories, revocation, restart, and privacy boundaries.
- [ ] Operator documentation explains minimum scopes, retention, disablement,
  refresh bounds, and the no-private-code/no-proficiency-inference boundary.

## Execution contract

### Expected implementation surface

- Add `src/riff/github_account.py`, an injected read-only GitHub account client,
  account repository, bounded candidate projection, and scope state machine.
- Add a migration only for durable account observations and selection decisions;
  reuse `github_repositories`, `github_repository_aliases`, and G26 onboarding.
- Extend `src/riff/adapter.py`/`src/riff/mcp_server.py` with bounded account
  reads and a confirmation-gated selection operation. Add CLI commands under
  `riff github account` and fixtures under `tests/fixtures/github/account/`.
- Add `tests/test_github_account.py`, update `README.md`,
  `docs/architecture.md`, and record a numbered privacy/scope decision.

### Canonical contracts and illegal states

- Account status is `ACTIVE`, `REVOKED`, or `SCOPE_NARROWED`; observation scope
  is `PUBLIC_METADATA` or `PUBLIC_METADATA_AND_ACTIVITY`.
- Every repository candidate includes `provider_repository_id`, `full_name`,
  `canonical_url`, `visibility`, `is_fork`, `is_archived`, `aliases`,
  `observation_id`, `observed_at`, `omitted_fields`, and `uncertainty`.
- No token, private raw response, or private code may appear in persistence,
  logs, fixtures, or tool results. A revoked account cannot refresh or select.
- Selection is `PROPOSED` until explicit user confirmation, then `ONBOARDED` or
  `DECLINED`; it cannot mutate profile state or upstream GitHub.

### Behavior and test map

| Condition | Required result |
|---|---|
| Valid public account fixture | Bounded candidates with account provenance |
| Private/inaccessible repository | Omitted with reason; no fetch of private content |
| Duplicate or renamed repository | One stable provider identity with aliases |
| Ambiguous natural-language selection | Clarification; no mutation |
| Confirmed selection | Exactly one G26 onboarding decision |
| Revoked/scope-narrowed account | Refresh/select denied; history retained |
| Repeated observation | Stable fingerprint and no duplicate candidates |
| Rate limit or partial page failure | Retry same page without advancing cursor |

Tests must map each row to named assertions in `tests/test_github_account.py`
and the scripted ChatGPT fixture; Postgres tests must verify restart-safe state.
