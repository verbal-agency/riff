# G48 — Restore provenance-safe live signal ingestion

**Status:** In Progress
**Depends on:** G30, G31, G35, G40, G41, G43
**Unlocks:** Trustworthy live dogfooding, calibrated publication, and G45 evaluation
**Canonical scenario:** `SC-LIVE-TRUST-001`

## Outcome

Riff has a small, verified live-ingestion lane that can supply signals for
riffing without confusing fixtures, generated test data, stale rows, or
unclassified evidence for external observations. The system reports source
health and provenance honestly, quarantines unsafe records, and publishes a
Riff only when the evidence meets the existing independence and provenance
ceilings.

This goal repairs the current gap between “a collection run completed” and
“Riff has trustworthy raw signals.” It does not require every registered source
to be healthy before dogfooding can resume.

## Current problem to close

The database contains live-labeled rows whose source names identify them as
fixtures, a large unclassified evidence population, many empty or never-run
sources, and failed or partial collection runs. A live worker must therefore
select evidence by verified origin and source eligibility rather than by a
`LIVE` label alone.

## Scope

- Define and enforce the write-time origin contract for `FIXTURE`, `LIVE`, and
  `UNCLASSIFIED` evidence across collectors, replays, fixtures, receipts, and
  source items.
- Add a provenance validator that rejects or quarantines rows when origin,
  source metadata, fixture markers, collection run ownership, and canonical URL
  disagree. Quarantine must preserve the raw row and explain the reason.
- Audit existing data and apply a non-destructive classification/backfill:
  known synthetic rows become fixture-owned, unverifiable rows remain
  unclassified/quarantined, and verified external rows retain their history.
- Define a small reviewed live-source set across the available source classes.
  Each source must have an owner, canonical root, fetch policy, last successful
  collection, and an explicit enablement decision. Disabled or unreviewed
  sources cannot enter the trusted lane.
- Replace source-state counts that only reflect registry/run presence with
  source-health metrics that include usable evidence yield, origin mix, last
  success, empty/partial/failed/never-collected state, and failure reason.
- Make the live worker select only trusted, source-attributed `LIVE` evidence;
  `FIXTURE` and `UNCLASSIFIED` evidence may be used for tests and diagnostics
  but never for a published live Riff.
- Make replay explicitly source-scoped or collection-run-scoped so a validation
  run cannot silently absorb same-day evidence from unrelated tests, fixtures,
  or prior operator runs.
- Propagate the resolved origin and ownership policy to `collection_runs`,
  including a deterministic rule for mixed-source runs and an auditable reason
  when a run remains unclassified.
- Report distinct audit reasons for disabled-source evidence, source/item/
  evidence origin mismatches, fixture markers, and missing source approval;
  operators must be able to tell a historical disabled row from a provenance
  violation.
- Classify known test and generated source identities as test-owned and disable
  them from live readiness without deleting their rows or raw evidence.
- Run a bounded clean live replay/collection against the reviewed set and
  record either a provenance-backed candidate with independent source roots or
  an honest insufficient-evidence result.
- Document the recovery commands, quarantine review, source-health report, and
  the operator-submitted URL fallback while broader collection is repaired.

## Non-goals

- Making all 2,625 registered sources healthy at once.
- Deleting evidence, rewriting raw content, or hiding historical anomalies.
- Treating source count, feed volume, GitHub stars, or job reposts as
  independent evidence.
- Lowering G29 confidence ceilings to force a daily recommendation.
- Adding a new paid provider or requiring live network access in automated
  tests.

## Acceptance criteria

- [x] An audit report gives total sources, enabled/reviewed sources, evidence
  counts by origin and source type, collection states, and a concrete anomaly
  list; it distinguishes `LIVE`-labeled rows from verified live provenance.
- [x] New fixture/test ingestion cannot write `LIVE` evidence, and a test
  fails closed when fixture markers or fixture-owned source metadata are paired
  with `LIVE` origin.
- [x] Existing known fixture rows are classified as fixture-owned or
  quarantined without deleting raw evidence; every reclassification is
  recorded in the data-governance audit trail.
- [x] Unclassified or quarantined evidence is excluded from live candidate
  generation and publication, while remaining available to diagnostics and
  fixture replay.
- [ ] A reviewed live-source registry records eligibility, canonical root,
  owner, fetch policy, and the latest health outcome; disabled, unreviewed,
  failed, and never-collected sources are visibly distinct.
- [ ] Replay accepts an explicit source or collection-run boundary, and the
  report proves that no unrelated same-day evidence was included.
- [ ] `collection_runs` receives the resolved origin, owner, and policy
  metadata from its source set; mixed or unresolved origins are recorded with
  an explicit reason rather than silently appearing as ordinary runs.
- [ ] Audit output distinguishes disabled-source history from actual
  provenance mismatches and missing approvals, with stable reason codes and
  actionable remediation.
- [ ] Known test/generated source identities are classified as test-owned and
  disabled from live readiness through a non-destructive, auditable operation.
- [x] The source-health report shows usable evidence yield and origin mix per
  source, not only collection-run counts, and one failed source cannot erase
  evidence from healthy sources.
- [ ] A bounded, source- or run-scoped clean live run either produces a
  candidate whose receipts link
  to verified external URLs from at least two independent roots, or returns an
  explicit insufficient-evidence/empty result with the blocking reasons.
- [x] The live worker, replay path, and publication path have tests proving
  that fixture and unclassified rows cannot enter a live Riff; tests use
  recorded inputs and make no live network or paid-provider calls.
- [x] Operator documentation gives one-line commands for audit, health
  inspection, quarantine review, clean replay, and URL-submission fallback.

## Deliverables

- Origin/provenance validation and quarantine service integrated at evidence
  write boundaries.
- Non-destructive audit/backfill migration and governance records.
- Reviewed-source eligibility and source-health report.
- Trusted live selection and publication guard.
- Clean live-run report plus recorded failure/insufficient-evidence examples.
- Updated operator documentation and focused regression tests.

## Implemented in the first slice

- Evidence ingestion now derives fixture origin from explicit retrieval metadata
  and established fixture markers in source identity, then propagates origin to
  source items, evidence versions, and retrievals.
- Live collection and replay require LIVE origin on the evidence, source item,
  and source, plus source enablement.
- data-quality audit reports origin totals, untrusted-live anomalies, fixture
  markers, and unreviewed sources.
- data-quality live-sources reports FIXTURE_ONLY, DISABLED,
  REVIEW_REQUIRED, UNCONFIGURED, EMPTY, and USABLE states.
- data-quality approve-live-source records explicit source approval; fixture
  markers and missing configuration are rejected.
- data-quality repair-origins --confirm REPAIR_ORIGINS performs only metadata
  reclassification and quarantine; it never deletes evidence.

The remaining work is to make the validation boundary explicit: review and
approve a small set of real sources, scope replay to those sources or their
collection run, carry origin metadata onto the run record, distinguish audit
failure reasons, and quarantine/disable known test identities. The current
database audit is a recovery baseline, not proof that the existing source
registry is already trustworthy.

## Execution contract

Reuse the existing origin/ownership policy from G35, source and collection-run
repositories, G43's extractor/replay boundary, and G29's confidence ceilings.
Do not introduce a second evidence store or silently reinterpret old rows.
Every classification decision must be deterministic, inspectable, and tied to
the source, collection run, policy version, and reason. If the reviewed live
set cannot yield enough evidence, preserve that result as an operational
finding rather than synthesizing a recommendation.

