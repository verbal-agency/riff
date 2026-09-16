# Riff v0.1 implementation goals

This roadmap translates the [Riff v0.1 PRD](../../Riff%20v0.1%20Product%20Requirements%20Document.md) into bounded goals that an implementation agent can execute one at a time. The PRD remains the product authority; these files define delivery order and verifiable slices.

## How 5.6 Luna should consume this roadmap

1. Read the PRD, this file, and exactly one active goal before changing code.
2. Inspect the current repository and preserve already-completed behavior.
3. Implement the smallest coherent solution that meets the active goal's acceptance criteria.
4. Make local implementation decisions when the goal intentionally leaves them open. Record consequential or hard-to-reverse decisions in `docs/decisions/`.
5. Do not pre-build later goals. Stable interfaces, migrations, and small enabling seams are allowed when required by the active goal.
6. Verify every acceptance criterion with automated evidence where possible. State any criterion requiring human judgment explicitly.
7. End with a concise handoff: changed files, decisions, verification run, acceptance status, and material follow-ups.

If a goal conflicts with the PRD, stop and surface the conflict instead of silently redefining the product. If implementation uncovers useful work outside the active goal, record it as a follow-up rather than expanding scope.

## Invariants across every goal

- Riff has one user in v0.1 and no authentication or team model.
- It is one Python application backed by Postgres, with one scheduled worker and a small interface-agnostic application API.
- Raw evidence is collected once and remains traceable; downstream reasoning primarily uses compact Evidence Receipts.
- Observation, hypothesis, and recommendation are distinct data and presentation concepts.
- Evidence quantity is not evidence independence. Root sources, organizations, authors, repositories, and source types matter.
- Capabilities are framework-independent; technologies remain separately represented.
- Model calls sit behind replaceable interfaces. Tests use deterministic fakes or recorded fixtures and do not require paid APIs.
- User profile context is retrieved narrowly. Do not send a full profile, full corpus, or full conversation when a relevant slice suffices.
- Zero Riffs is a valid daily result. The system must not manufacture novelty.
- Only the user can approve `RIFF -> EXPLORATION` and `EXPLORATION -> PRD`.
- Coding-agent execution, autonomous PRs, complex frontend work, and every other PRD v0.1 non-goal remain out of scope.

## Goal order

| Goal | Outcome | Depends on |
|---|---|---|
| [G00](G00-foundation.md) | Executable application foundation | — |
| [G01](G01-provenance-store.md) | Provenance-first evidence store | G00 |
| [G02](G02-writing-ingestion.md) | Incremental ingestion framework and technical-writing source | G01 |
| [G03](G03-github-ingestion.md) | Incremental GitHub evidence | G02 |
| [G04](G04-job-ingestion.md) | Incremental job-market evidence | G02 |
| [G05](G05-evidence-receipts.md) | Versioned evidence compression and extraction | G02–G04 |
| [G06](G06-capability-model.md) | Reversible capability normalization | G05 |
| [G07](G07-user-capability-profile.md) | Evidence-backed personal capability model | G06 |
| [G08](G08-signal-engine.md) | Deterministic candidate generation and ranking | G06–G07 |
| [G09](G09-daily-riffs.md) | Deep arguments and zero-to-three daily Riffs | G08 |
| [G09a](G09a-local-daily-smoke.md) | Locally executable database-backed daily Riff smoke path | G09 |
| [G09b](G09b-ingestion-source-selection.md) | Reviewed concrete ingestion-source plan for dogfood | G09a |
| [G10](G10-decision-loop.md) | Investigation, lifecycle, and semantic decision memory | G09b |
| [G11](G11-explorations.md) | Human-approved bounded Explorations | G10 |
| [G12](G12-prds-and-agent-goals.md) | Learning PRDs and executable goal decomposition | G11 |
| [G13](G13-daily-operations.md) | Reliable scheduled end-to-end daily run | G09–G12 |
| [G14](G14-chatgpt-adapter.md) | Conversational ChatGPT-facing adapter | G10–G13 |
| [G15](G15-dogfood-release-gate.md) | Evaluated v0.1 dogfood release | G00–G14 |
| [G16](G16-rss-source-expansion.md) | Expand the technical-writing RSS source set | G15 |
| [G17](G17-engineer-authored-sources.md) | Identify and qualify engineer-authored sources | G16 |
| [G18](G18-github-discovery-evaluation.md) | Evaluate the GitHub discovery process | G15 |
| [G19](G19-engineer-rss-integration.md) | Integrate approved engineer-authored RSS sources | G16, G17 |
| [G20](G20-bounded-github-discovery.md) | Implement bounded GitHub topic/search discovery | G18 |
| [G21](G21-automated-job-collection-and-url-intake.md) | Automate compliant job collection and listing URL intake | G04 |
| [G22](G22-postgres-configuration-and-persistence-verification.md) | Configure Postgres and verify persistence boundaries | G00, G04, G21 |
| [G23](G23-chatgpt-tool-loop-client.md) | Wire the ChatGPT tool-loop client | G14, G22 |
| [G24](G24-chatgpt-connector-and-e2e-acceptance.md) | Connect ChatGPT and run end-to-end conversation | G22, G23 |
| [G24a](G24a-native-chatgpt-mcp-surface.md) | Expose a native ChatGPT MCP surface and complete external acceptance | G22, G23 |
| [G25](G25-meaningful-github-discovery-and-integration.md) | Make GitHub discovery meaningful and pipeline-integrated | G18, G20, G22 |
| [G26](G26-github-project-understanding.md) | Build an evidence-backed understanding of user GitHub projects | G03, G22, G25 |
| [G27](G27-project-aware-personalized-recommendations.md) | Recommend extensions to existing projects | G08, G11, G12, G23, G24, G26 |
| [G28](G28-opportunity-context-and-execution-riffing.md) | Model opportunity context and riff on execution candidates | G21, G24, G26, G27 |
| [G29](G29-provenance-aware-confidence-calibration.md) | Calibrate Riff confidence from provenance quality | G05, G08, G09, G22 |
| [G30](G30-data-quality-remediation-and-rca.md) | Repair persisted data quality and close the feedback loop | G22, G29 |
| [G31](G31-engineer-source-provenance-operations.md) | Execute and verify engineer-source provenance collection | G17, G19, G22, G30 |
| [G32](G32-natural-language-conversational-continuity.md) | Make conversational Riff exploration natural and context-preserving | G10, G11, G12, G23, G24a |
| [G33](G33-github-account-observation.md) | Observe the user's GitHub account with explicit scope | G03, G22, G24a, G26 |
| [G34](G34-github-source-monitoring-and-quantitative-discovery.md) | Monitor selected repositories and run quantitative GitHub discovery | G18, G20, G25, G26, G33 |
| [G35](G35-data-origin-ownership-and-retention.md) | Govern data origin, fixture ownership, retention, and safe cleanup | G22, G27, G30, G31 |
| [G36](G36-personalized-github-guidance-and-memory.md) | Turn monitored GitHub changes into personalized guidance and durable memory | G26, G27, G32, G33, G34, G35 |

G03 and G04 may be implemented in either order. All other goals should normally follow the table.

## PRD coverage

| PRD v0.1 concern | Owning goals |
|---|---|
| Three-source incremental evidence and deduplication | G01–G05 |
| Provenance from argument back to raw source | G01, G05, G09 |
| Capability/technology separation and normalization | G06 |
| Public, private, and generated capability evidence | G07 |
| Novelty, relevance, independence, and adversarial ranking | G08 |
| Zero-to-three complete daily arguments | G09 |
| Investigation, feedback, rejection, and resurfacing memory | G10 |
| Explicit human authority over both promotions | G10–G12 |
| Bounded collaborative Explorations | G11 |
| Learning PRDs and outcome-oriented executable goals | G12 |
| Token-efficient scheduled daily operation | G13 |
| Initial conversational ChatGPT experience | G14, G23, G24 |
| Extraction, normalization, signal, product, and dogfood evaluation | G05, G06, G08, G15 |
| Full Section 33 release acceptance | G15 |
| RSS/Atom source expansion and feed-quality controls | G16 |
| Engineer-level attribution and source discovery | G17 |
| Engineer-authored RSS selection and pipeline integration | G17, G19 |
| GitHub discovery recall, precision, and bounded-query policy | G18 |
| Bounded GitHub discovery and reviewed scope promotion | G18, G20 |
| Meaningful GitHub discovery and pipeline integration | G25 |
| User-owned GitHub project understanding | G26 |
| Project-aware personalized recommendations | G27 |
| Opportunity constraints, candidate generation, and iterative execution riffing | G28 |
| Provenance-aware confidence, independence, and synthetic-evidence disclosure | G29 |
| Persisted data quality, collection health, and RCA | G30 |
| Data origin, fixture ownership, quarantine, retention, and safe cleanup | G35 |
| Engineer-source collection provenance and evidence quality | G31 |
| Automated job collection and listing URL intake | G04, G21 |
| User-authorized GitHub account observation and project selection | G33 |
| Selected-repository monitoring and quantitative discovery | G34 |
| Personalized repository guidance and bounded memory | G36 |

## Canonical project scenarios

These short IDs keep goal handoffs tied to project-level outcomes without duplicating the PRD's full acceptance text.

- `SC-FOUNDATION-001` — A clean checkout can initialize, run, report health, and execute one worker cycle.
- `SC-EVIDENCE-001` — New evidence is incrementally stored once and remains traceable to its source and raw snapshot.
- `SC-CAPABILITY-001` — Different technologies can normalize to a capability without collapsing distinct capabilities.
- `SC-PROFILE-001` — Riff distinguishes public, private, hands-on, studied, and unknown capability evidence.
- `SC-SIGNAL-001` — Correlated or established volume is down-weighted while independent weak signals remain inspectable.
- `SC-RIFF-001` — A daily request returns zero to three provenance-backed arguments with counterarguments and personalization.
- `SC-DECISION-001` — User decisions persist semantically and affect later ranking/resurfacing.
- `SC-DELIVERY-001` — An explicitly approved Riff becomes a bounded Exploration, learning PRD, and agent-ready goals.
- `SC-DOGFOOD-001` — Dogfooding produces a user-reviewed investigation moment or stops broader development for signal improvement.
- `SC-RSS-001` — Riff ingests a reviewed, fixture-replayable RSS/Atom source set without mistaking syndication or feed volume for independent evidence.
- `SC-ENGINEER-SOURCE-001` — Riff can qualify a named engineer's source and preserve authorship, employer, and correlation provenance.
- `SC-GITHUB-DISCOVERY-001` — Riff can compare bounded GitHub discovery strategies before promoting one into collection.
- `SC-JOB-001` — A permitted job source or user-submitted listing URL becomes provenance-backed, decomposed job evidence through the same cron and terminal path.
- `SC-DB-001` — A clean local Postgres database can migrate, persist G21 job flows, and pass the complete database-backed regression suite.
- `SC-CHATGPT-001` — A bounded model tool loop can read Riff state and render a grounded conversational response.
- `SC-CHATGPT-002` — A supported ChatGPT connector can complete the approved read-and-promote workflow against persisted Riff state.
- `SC-CHATGPT-003` — ChatGPT Developer Mode connects to Riff's MCP `/mcp` surface and completes the approved read-and-promote workflow with visible tool approvals.
- `SC-GITHUB-DISCOVERY-002` — Riff discovers user-relevant GitHub candidates and integrates only explicitly promoted scopes into evidence collection.
- `SC-PROJECT-MAP-001` — Riff maintains a versioned, evidence-backed understanding of selected user GitHub projects.
- `SC-EXTEND-001` — Riff recommends extending an existing project when the evidence supports it, while preserving a greenfield alternative.
- `SC-EXECUTION-RIFF-001` — Riff extracts opportunity constraints, detects obvious platform requirements, generates execution candidates, and preserves iterative riffs until the user chooses a distinctive direction.
- `SC-EPISTEMIC-001` — Riff distinguishes an interesting hypothesis from a well-supported claim and shows what provenance is needed next.
- `SC-DATA-QUALITY-001` — Riff repairs persisted metadata and stale collection state, then explains every remaining data anomaly.
- `SC-CHATGPT-004` — Riff carries a concept through natural-language investigation and refinement until the user explicitly requests a PRD.
- `SC-GITHUB-ACCOUNT-001` — Riff observes a user-authorized GitHub account, presents bounded repository candidates, and onboards only explicitly selected projects.
- `SC-GITHUB-MONITOR-001` — Riff monitors selected repositories and queues bounded, quantitatively qualified discovery candidates without silently enabling collection.
- `SC-PERSONALIZED-GITHUB-001` — Riff explains meaningful changes in a selected repository, connects them to the user's bounded project/profile context, and records inspectable guidance feedback without treating ownership as proficiency.

## Current handoff

G00 through G24 are complete. G23's provider-neutral model tool loop now runs
against persisted Postgres adapter state; G24's provider-neutral HTTP connector
and native ChatGPT acceptance now include a redacted external read-and-promote
transcript, Inspector protocol checks, and a recorded human evaluation. G24a now exposes
the native MCP `/mcp` transport, passes Inspector and ChatGPT acceptance, and
is complete as a transport/lifecycle goal; its rough interaction quality is
routed to G32. G25's offline, fixture-backed discovery and review slice and
its promoted-scope G03/Postgres integration are complete. G26 now maintains a
separate user-approved project inventory and versioned, evidence-backed map
from bounded G03 artifacts; G27's deterministic project-aware recommendation
implementation is complete. The user's review established a conditional policy:
use project-aware recommendations only when a legitimate evidence-backed seam
exists; otherwise prefer greenfield.
G28 is complete: it adds opportunity-context modeling and iterative execution
riffing so those recommendations become a search over distinctive,
evidence-producing demonstrations rather than a single generic project
suggestion. Its selected downstream direction is a comparative memory lab using
one representative Riff workflow; implementing that artifact is separate from
Riff's core. G29 then
calibrates confidence from provenance quality so synthetic or thin evidence is
not presented as an established claim.
G30 then repairs persisted metadata and stale collection state, provides source
coverage, and closes the loop with repeatable RCA before real-source dogfooding.
G31 is the operational follow-up for engineer-source provenance: it turns only
per-source-reviewed native RSS entries into evidence, then verifies that the
person, employer, root, and correlation metadata survive collection. G17's
engineer-source roster and attribution contract were approved by the user; G31
approved and collected the initial Simon Willison, Eugene Yan, and Lilian Weng
selections, followed by operator enablement of 13 additional validated native
feeds. The three URL-only candidates remain disabled pending an adapter
decision. G19 added the
fail-closed selection and attribution seam. G20
implements bounded topic/search discovery
from the G18 decision and keeps discovered scopes behind review. G21 adds the
shared scheduled and terminal path for compliant job collection plus
one-listing URL intake. The earlier
durable-execution/observability mini-project and workflow-reconciliation
investigation remain in `docs/backlog.md`.
G32 is complete: it adds disposable natural-language handles and bounded
rendering so follow-up exploration no longer requires UUID/tool relaying,
dated no-result fallback, alternate recommendations, and read-only scenario
mapping. The user confirmed the updated flow is an improvement and that
follow-ups feel solid. G33 is complete: it adds explicit, scope-limited
observation of the user's GitHub account, bounded public repository candidates,
confirmation-gated selective onboarding into G26, and auditable revoke/scope
narrowing. G34 is complete: it adds durable monitoring of selected repositories
and quantitative search rules that can auto-queue or propose disabled scopes
without bypassing review.
G35 is ready for data-origin, fixture-ownership, retention, and safe-cleanup
hardening; G36 remains queued behind G34 and G35.
G36 then turns those monitored deltas into personalized, evidence-backed
guidance through separate evidence, project, decision, guidance, and
disposable-conversation memory layers; it must not infer proficiency or persist
unbounded conversation history.

```text
G22 is complete. Keep live job sources disabled until terms/robots
and retention are reviewed; the 16 reviewed G31 engineer RSS selections are
enabled, while URL-only engineer candidates remain disabled.
```

After a goal is accepted, update its status to `Complete` and change every newly unblocked goal from `Queued` to `Ready`. Use `In progress` only while an agent is actively implementing that goal.

## Definition of done for a goal

A goal is complete only when:

- its deliverables exist and are integrated rather than isolated demonstrations;
- every acceptance criterion is either verified or explicitly identified as pending human evaluation;
- tests cover the stated happy path and the material failure paths;
- migrations and interfaces are backward-compatible with completed goals, or the intentional break is documented;
- configuration, setup, and operator-facing behavior introduced by the goal are documented;
- no secrets, private evidence, paid-provider requirement, or live-network dependency is embedded in the test suite;
- the repository's full verification suite passes.

Passing tests alone is not proof of completion when the goal requires a user-visible or operator-visible behavior.

## Completion report contract

Each Luna run should finish with:

```text
Goal: Gxx — name
Status: complete | incomplete | blocked
Outcome delivered: ...
Key decisions: ...
Verification: command/result ...
Acceptance criteria: pass/fail list ...
Follow-ups: only work not required by this goal ...
```

G15 was completed only after the user recorded the qualitative judgment; future
cycles must preserve that human authority for any new release gate.
