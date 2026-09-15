# G34 — Monitor selected repositories and run quantitative GitHub discovery

**Status:** Queued
**Depends on:** G18, G20, G25, G26, G33
**Unlocks:** Continuously refreshed project evidence and high-recall source expansion
**PRD references:** Sections 7.2, 8, 21–22, 24.3, 27–29, 33
**Canonical scenario:** `SC-GITHUB-MONITOR-001`

## Outcome

Riff can monitor explicitly selected GitHub repositories on the same scheduled
and terminal paths, run bounded search strategies with quantitative thresholds,
and add promising candidates to a reviewable queue. Safe policy-approved
matches may be auto-queued or auto-onboarded into a disabled scope, but no
search result silently becomes live collection or mutates an upstream repo.

## User-visible proof

The user can ask ChatGPT to watch or unwatch a repository, see its last run and
new evidence, request a bounded search, and inspect why a candidate was queued.
The user can approve a candidate or configure a quantitative rule that adds
only bounded, provenance-bearing candidates to a disabled review queue.

## Scope

### 1. Source monitoring

- Add a durable watch record for selected G03/G26 repositories with cadence,
  artifact surfaces, page/item/body/request limits, retention, and policy
  version.
- Reuse `GitHubIngestionRunner`; persist run health, cursors, new/duplicate/
  failed counts, rate-limit state, and changed project-snapshot linkage.
- Provide one-shot terminal and cron-compatible commands plus a bounded status
  and last-run report. Watch disablement stops future collection without erasing
  prior evidence.

### 2. Quantitative discovery and safe addition

- Run bounded repository searches using G20's injected/live boundaries and
  preserve query, seed, page, root, organization, author, and correlation
  provenance.
- Support explicit quantitative predicates such as minimum independent roots,
  source-type diversity, recent release/change count, or project-fit score;
  popularity alone can never qualify a candidate.
- Route matches to `AUTO_QUEUED` (review queue) or `DISABLED_SCOPE_PROPOSED`
  according to a versioned user-reviewed policy. Actual collection enablement
  remains an explicit user decision.
- Deduplicate search candidates against account-observed repositories, G03
  sources, G26 inventory, aliases, forks, mirrors, and prior queue entries.

### 3. ChatGPT and operator workflow

- Add bounded tools for watch/unwatch, monitor status, quantitative search, and
  candidate review/add. Natural-language repository references must resolve
  through account/project context or ask for clarification.
- Return compact evidence deltas and candidate reasons; do not return full
  repository contents or credentials.
- Keep monitoring and discovery read-only against GitHub and confirmation-gated
  for local source/watch mutations.

## Non-goals

- Broad crawling, unbounded search, automatic live-source enablement, private
  code, repository writes, issue/PR actions, or model-generated thresholds that
  bypass policy review.
- Replacing G03/G20/G25 collection or turning quantitative popularity into
  capability evidence.

## Acceptance criteria

- [ ] A user-approved repository watch persists scope, cadence, bounds, status,
  and last-run health; terminal and cron invoke the same one-shot path.
- [ ] A monitored fixture run reuses G03, stores only new evidence, preserves
  cursors/rate-limit outcomes, and links changed artifacts to G26 refresh input.
- [ ] A bounded quantitative search emits deterministic candidates with query,
  threshold, root/correlation, and uncertainty provenance.
- [ ] Candidates meeting a reviewed rule can be auto-queued or proposed as a
  disabled scope; no candidate is silently enabled or collected live.
- [ ] Duplicate, alias, fork, mirror, popularity-only, archived, and
  insufficient-independence candidates are excluded or labeled deterministically.
- [ ] ChatGPT can watch, inspect status, search, and review/add a candidate with
  stable natural-language handles and explicit confirmation for mutations.
- [ ] Offline, Postgres, and scripted conversational tests cover scheduling,
  replay, changed/duplicate evidence, rate limits, threshold boundaries,
  disablement, privacy, restart, and no-auto-enable behavior.
- [ ] Operator documentation defines cron/terminal commands, policy review,
  quantitative rule versioning, rollback, retention, and source disablement.

## Execution contract

### Expected implementation surface

- Add `src/riff/github_monitoring.py` for watch policy, run/report state, and
  quantitative candidate rules; reuse `src/riff/github_ingestion.py` and
  `src/riff/github_discovery.py` rather than duplicating collectors.
- Add additive migrations for watch records and candidate decisions only when
  existing source/cursor tables cannot preserve the contract.
- Extend adapter/MCP and CLI surfaces under `riff github monitor` and
  `riff github search`; add fixtures under
  `tests/fixtures/github/monitoring/` and focused tests in
  `tests/test_github_monitoring.py`.
- Update `README.md`, `docs/architecture.md`, and a numbered policy decision.

### Canonical contracts and illegal states

- Watch status is `ACTIVE`, `DISABLED`, or `REVOKED`; candidate disposition is
  `AUTO_QUEUED`, `DISABLED_SCOPE_PROPOSED`, `APPROVED`, `REJECTED`, or
  `PROMOTED`.
- A quantitative rule includes `rule_id`, `policy_version`, bounded predicates,
  minimum independent roots, maximum candidates, request/page limits, and an
  explicit action (`QUEUE` or `PROPOSE_DISABLED_SCOPE`).
- `PROMOTED` requires an explicit user confirmation and never implies enabled
  collection. A disabled/revoked watch cannot collect or advance its cursor.
- Every candidate and run carries query/policy fingerprints, evidence/source
  IDs, root/correlation metadata, threshold evaluation, and uncertainty.

### Behavior and test map

| Condition | Required result |
|---|---|
| Watched repository, first run | G03 evidence and durable run/cursor state |
| Unchanged repeat | No new evidence; duplicate counts and stable report |
| New release/README/issue | One new G03 artifact; G26 can refresh from it |
| Rate limit or partial page | Retry/replay same page; no skipped cursor |
| Search meets reviewed thresholds | Deterministic `AUTO_QUEUED` candidate |
| Search fails independence/popularity guard | Filtered candidate with reason |
| Confirmed promotion | Disabled scope only; no automatic enablement |
| Disabled/revoked watch | No network call or cursor mutation |

Map each row to named offline/Postgres assertions in
`tests/test_github_monitoring.py` and a ChatGPT scripted scenario. Add a human
evaluation comparing manually selected versus quantitatively queued sources.
