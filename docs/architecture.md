# Riff v0.1 foundation architecture

G00 establishes one Python application with three process entry points: the HTTP API, a one-shot scheduled worker, and a migration command. Later goals add domain behavior behind these seams; this goal deliberately creates no evidence or capability tables.

## Choices

- **Python package:** `src/riff` with `pyproject.toml` and Hatchling metadata. This keeps imports explicit and supports normal editable installs.
- **HTTP API:** FastAPI. It provides typed, small endpoints and a straightforward interface boundary for the future ChatGPT adapter.
- **Database driver:** `psycopg` 3. The application uses direct parameterized SQL for the small foundation and can introduce a repository abstraction as domain tables arrive.
- **Migrations:** numbered SQL files applied by the in-process migration runner. Migrations are explicit and transactional; application startup never mutates schema.
- **Validation/configuration:** standard-library dataclasses and URL validation for the foundation. Domain schemas can add a validation library when G01 requirements justify it.
- **Tests:** pytest with HTTPX for API tests. Postgres tests are separately marked and require an explicitly configured database URL.
- **Scheduling:** an external simple scheduler (cron, launchd, or equivalent) invokes the tested one-shot worker. No queue or workflow service is needed in v0.1.

## Boundaries

Imports have no network or database side effects. Configuration is loaded at command/request boundaries. The API owns health behavior, the worker owns orchestration entry, and the migration command owns schema changes. Secrets are accepted only through environment configuration and are never emitted by structured logs.

## G02 ingestion

Technical-writing sources are a manually editable JSON registry synchronized into Postgres source configuration. The first adapter is RSS/Atom over an injectable HTTP boundary. A one-shot runner records each collection run and item result, writes evidence through the G01 repository, and advances a source cursor only after that evidence transaction commits. Network failures are classified as transient or permanent; malformed entries are quarantined while valid siblings continue. Hacker News discovery is not enabled in this slice.

## G03 GitHub ingestion

GitHub collection uses an injected, read-only REST client and explicit
repository endpoints. Repository provider IDs are persisted separately from
display names so renames and organization transfers retain one logical identity
and an alias history. Releases, issues, and README snapshots become G01
evidence versions with normalized artifact metadata, author identity, fork/
mirror flags, and bounded content. G02 page cursors advance only after a whole
page is durable; replaying a completed page is safe because G01 deduplicates
provider items and content hashes. Credentials are process-only (`GITHUB_TOKEN`)
and never persisted.

## G04 job-market ingestion

Job evidence enters through a schema-versioned JSON export/import seam so
development and evaluation do not depend on a fragile or non-permitted job
site. The runner uses the G02 run/cursor/item contracts, stores employer
identity and reversible aliases separately from posting evidence, and preserves
retrieval history for exact reposts and expired listings. Missing job metadata
remains null; no compensation, seniority, or date is inferred.

## G21 automated job collection and URL intake

G21 keeps job collection as one Python one-shot service so terminal execution
and cron invoke identical logic. A schema-versioned job policy describes the
access method, terms/robots review, allowlist, cadence, request/page/item/body/
redirect bounds, retries, retention, and fixture reference. The repository
defaults keep live sources disabled until review; a `USER_URL` source permits
one operator-submitted public listing without enabling a crawl.

`HttpJobFetcher` validates schemes, credentials, DNS results, allowlists, and
every redirect before a bounded read-only request. Recorded fixtures use the
same fetch/decomposition interface. `JobPosting` JSON-LD is preferred, with a
bounded HTML fallback when the policy permits it. Normalized fields and raw
content flow through the G04 importer/evidence store, preserving retrieval
history, exact-repost deduplication, changed-content versions, employer
identity, parser/policy metadata, and synthesis-ready receipt inputs. No
credentials, browser session, private-network access, arbitrary link following,
application action, or model call is part of this seam.

## G20 bounded GitHub discovery

Discovery is a bounded, file-backed review queue in front of the existing G03
collector. `config/github_discovery.json` limits query terms, pages, candidates,
requests, retries, and contributor expansion; it is disabled until an operator
reviews the policy. The fixture-backed `github discover` command normalizes
stable provider IDs, aliases, roots, organizations, fork/mirror flags, bot
markers, query and seed provenance, author attribution, correlation metadata,
relevance reasons, and uncertainty, then applies deterministic duplicate,
popularity-only, and root-concentration filters. Capability, repository,
engineer, and organization inputs become bounded queries. A candidate must
transition from `NEW` to `APPROVED` through the review command before the
`PROMOTE` token can write a single disabled scope to
`config/github_sources.json`. The existing G03 collector remains the only path
that stores GitHub evidence. Candidates receive stable relevance scores for
review ordering; popularity never increases a score. Live discovery is
explicit, read-only, token-safe, and never part of normal tests.

## G05 evidence receipts

Receipts are compact, schema-versioned projections of one immutable raw
evidence version. A receipt is cache-keyed by evidence content hash, extractor
version, and prompt/schema version, so unchanged evidence is not reprocessed;
changing the extractor retains the prior receipt as a separate version.
Relevant spans are validated against the stored raw text using exact offsets and
excerpts, and claims may cite only validated span IDs. Extraction providers sit
behind an injected interface, while validation and retry outcomes are recorded
in receipt attempts. Receipt retrieval is compact by default and never loads
the raw body; callers explicitly join to evidence when they need source text.

## G06 capability normalization

G06 keeps transferable capabilities and concrete technologies as separate,
stable entities. Receipt candidates are preserved as immutable mappings with
confidence, rationale, and explicit proposed/accepted/rejected/superseded
states. Technology-to-capability relationships are many-to-many. Review actions
append decisions, so accept, reject, remap, split, and undo are reversible
without rewriting receipts or losing provenance. The shipped normalizer is a
bounded deterministic alias seam; model-assisted normalization can be injected
later without changing the relational contract.

## G07 user capability profile

The profile layer stores capability-scoped evidence with explicit level,
visibility, origin, confidence, and attestation state. Private Experience
Ledger entries are user-attested and are available only in authorized personal
views; public/export queries filter them at the repository boundary. Gap
assessments are recomputable snapshots with retained rationale and uncertainty.
Corrections, archives, and semantic feedback append history rather than
erasing evidence. GitHub or Riff-artifact mentions remain candidate/unknown
evidence until an explicit assessment establishes a stronger level.

## G08 signal engine

The signal engine groups receipt evidence by normalized capability and computes
versioned, deterministic feature vectors. Frequency remains separate from
independence: repeated items sharing an employer, repository, author, or root
source are down-weighted, while source-type diversity and recent change support
trend eligibility. Every rank run stores its input fingerprint, correlation
groups, feature values, weights, contributions, and an explicit trend versus
observation decision. Replaying the same inputs and policy returns the existing
run without duplicate candidates.

## G09 daily Riffs

G09 consumes only a bounded, ranked candidate set. `RiffContextAssembler`
retrieves candidate-relevant receipt summaries, profile slices, and decision
IDs; it rejects unknown, failed, or snapshot-only receipts before a provider is
called. A replaceable `ReasoningProvider` returns structured fields, and the
deterministic validation/publication gate requires distinct observation,
hypothesis, and recommendation text plus a counterargument, alternative
explanation, falsification conditions, and eligible citations. The daily run is
fingerprinted by date, policy version, and selected inputs, so retries reuse the
persisted result and never call the provider again. `GET /riffs/daily/{date}` is
a stable read-only presentation surface; it does not invoke reasoning.

For local verification, `riff daily generate --file ...` seeds only the
fixture's raw evidence and successful receipts, then runs the same persisted
service used by the API. Repeating the command with the same date, fixture, and
policy returns the existing run without provider calls or duplicate rows.

## G09b source selection

The source plan is kept in a separate, secret-free manifest so access terms,
retention, fixture replay, and fallback decisions are reviewable before G02–G04
collection is enabled. `source validate-manifest` performs structural and
credential checks without contacting any source. Pending live sources remain
disabled until an operator records a terms/retention review.

## G10 decision loop

Decision records preserve the exact user reason, structured semantic
implications, evidence snapshot, policy version, and append-only correction
history. Lifecycle transitions are validated under row lock and mirrored in a
status-history table. Investigation joins only the Riff's supporting and
counterevidence plus its bounded context; it does not load the corpus. A
material-change resurface records the prior rejection, new receipt IDs, and a
versioned explanation. Model/system actors cannot approve exploration.

## G11 Explorations

An Exploration is created only from a traceable user `APPROVE_EXPLORATION`
decision. The deterministic generator preserves the PRD schema fields, then
proposes materially different experiments with capability targets,
representative technologies, a five-step learning pipeline, effort
assumptions, selection-rule assessments, and an artifact or measurement.
Exploration versions and events retain semantic refinement/rejection history.
The API can create, inspect, refine, and select an experiment; selection is a
deliberation endpoint and does not create a PRD or approve one.

## G12 learning PRDs and goals

PRD generation has a second, independent user approval boundary after an
Exploration experiment is selected. The deterministic project generator emits
every Section 19 field plus an ordered, acyclic set of goals with objective
acceptance checks, verification evidence, and a 4–20 focused-hour budget.
Projects retain source Exploration and approval IDs, support stable structured
and Markdown export, and regeneration appends a new project version rather
than erasing prior provenance. This layer does not execute agents or publish
artifacts.

## G13 daily operations

`DailyPipeline` coordinates the existing stage services behind a durable
`(run_date, policy_version)` identity. Each stage is independently persisted
with status, attempts, counts, duration, errors, and optional model usage;
completed stages are skipped on resume. A row-locked claim makes concurrent
attempts inspectable no-ops, while policy changes intentionally fork a new run.
The worker's fixture mode and the documented scheduler invoke the same
one-shot path, and `/operations/{run_id}` exposes the operator report.

## G14 conversational adapter

The `riff-tools-v1` adapter is a stateless dispatch layer over the application
repositories. It returns persisted daily results, bounded Riff investigation
and provenance, public profile/capability slices, decisions, Explorations,
PRDs, exports, and operation reports. Promotion mutations require a literal
user confirmation token plus the core persisted approval, so model text cannot
silently cross either boundary. Restarting the adapter loses no canonical
state.

## G23 ChatGPT tool loop

The outer conversational client is intentionally separate from Riff's
application state. It receives a model turn, validates typed tool calls against
the adapter catalog, invokes `POST /adapter/tools/{tool_name}`, and returns a
bounded tool result to the model until a final response is produced. The loop
has explicit turn, call, timeout, context, and result-size budgets; refusal and
budget failures use typed error codes; and it records a redacted tool trace.
Model-generated confirmation tokens are never trusted; promotion tools receive
`USER_CONFIRMED` only from the outer user-confirmation boundary.

`src/riff/chat_loop.py` supplies provider-neutral protocols and deterministic
scripted fakes. G24 adds `src/riff/connector.py` as a bounded HTTP implementation
of the same `ToolAdapter` protocol. It discovers `riff-tools-v1`, calls the
existing adapter endpoints without retries, caps response size and timeout, and
optionally uses `RIFF_ADAPTER_TOKEN`; no provider or model state is persisted.
Loopback HTTP is limited to local dogfooding, while deployment requires HTTPS,
restricted network origin, and secret-managed token rotation. A future MCP or
provider SDK can replace the transport without changing Riff's invariants.

## G32 natural-language continuity

`ConversationContext` and `ConversationSession` add a disposable, bounded alias
layer around the provider-neutral loop. Tool results bind labels such as
“the top Riff” or “candidate 1” to canonical IDs for the current session; a
single match resolves silently, while ambiguous or stale labels return typed
clarification errors. `NaturalLanguageRenderer` sends the model compact
summaries with citations and uncertainty while retaining raw IDs only in the
audit trace. Session context is not persisted and can be reconstructed by
rebinding an explicit persisted ID after restart. Confirmation tokens still
come only from the outer user boundary.

## G24a native MCP transport

`src/riff/mcp_server.py` uses the official Python MCP SDK's stateless
Streamable HTTP server and mounts its canonical `/mcp` route alongside the
existing FastAPI application. Every handler delegates to `RiffToolAdapter`; no
MCP code opens a database connection or implements a second domain API. SDK
schemas are generated from typed wrappers, and `ToolAnnotations` mark reads as
read-only/idempotent while decisions and promotion operations are state
changing. The mounted transport inherits the same optional bearer token and
keeps the SDK's DNS-rebinding host/origin checks enabled. The MCP session
manager runs in the parent FastAPI lifespan so restarts discard only transport
state; Postgres remains the sole canonical store.

## G26 GitHub project understanding

`src/riff/project_map.py` keeps user-approved GitHub repositories in a project
inventory separate from generated PRD projects. Refreshes read only persisted
G03 repository, README, release, and issue artifacts, cap the artifact count,
and write immutable versioned summaries in `github_project_snapshots`. Claims
carry evidence IDs and optional receipt/mapping IDs plus parser/policy
versions, confidence, and observed/inferred/unknown status. Repeated input is
content-addressed and returns the existing snapshot; changed input links a new
version to its predecessor. Archive and onboarding are explicit user actions.
No code is executed, private content is fetched, or profile state is mutated.

## G33 GitHub account observation

`src/riff/github_account.py` provides an injected, read-only account observer
with a fixture replay seam and the existing bounded `HttpGitHubFetcher`. A
public-metadata observation stores stable provider account identity, scope,
consent, status, timestamps, and an input fingerprint; repository candidates
store only bounded identity/visibility fields, aliases, omission reasons, and
uncertainty. Raw account responses, authorization headers, tokens, and private
code never enter Postgres, logs, fixtures, or adapter results.

The `github_account_observations`, candidate, event, and selection tables keep
observation history separate from G03 evidence and the G26 project inventory.
Repeated observations with the same scope and fingerprint are idempotent.
Revocation and scope narrowing append an event and block later selection; a
confirmed selection links exactly one repository to G26 while preserving the
observation and selection IDs as audit-only provenance. The adapter/MCP expose
bounded status/list reads and a confirmation-gated onboarding operation; the
terminal exposes the same observe/status/list/select/decline/revoke/narrow
operations. Account observation does not replace G03 collection or infer user
proficiency from ownership.

## G34 GitHub monitoring and quantitative discovery

`src/riff/github_monitoring.py` adds explicit repository watches and a durable
monitor-run ledger on top of G03. A watch references an existing configured
source, records cadence/scope/policy, and reuses `GitHubIngestionRunner`, so
terminal and cron invocations share retry, duplicate, evidence, and cursor
behavior. Disabled or revoked watches cannot call GitHub or advance a cursor;
prior evidence remains available for G26 snapshots.

Bounded quantitative search evaluates injected or live rows against a reviewed
`QuantitativeRule`, persisting query/policy fingerprints, independence and
threshold evaluations, correlation metadata, and uncertainty. Forks, mirrors,
aliases, archived repositories, popularity-only hits, and insufficiently
independent evidence are labeled deterministically. Accepted rows are
`AUTO_QUEUED` or `DISABLED_SCOPE_PROPOSED`; review is required before
promotion, and promotion never enables collection. CLI and MCP share these
boundaries with confirmation-gated state changes.

## G35 data origin and retention

`src/riff/data_governance.py` supplies the origin/owner policy shared by source,
evidence, run, project, and recommendation records. New writes can explicitly
label `LIVE`, `FIXTURE`, `TEST`, `QUARANTINED`, or `UNCLASSIFIED`; the known
fixture backfill is deliberately narrow. Reports filter non-live data by
default, while a bounded audit mode exposes origin labels and policy versions.

Cleanup is a two-phase preview/apply operation scoped to an origin and owner.
It checks exploration dependencies, deletes only owned project projections in
dependency order, and writes an audit record; live evidence, daily Riffs, and
operational history are never selected. Malformed payloads are preserved in an
append-only quarantine ledger. Retention remains dry-runnable and records an
immutable archival decision without deleting evidence history.

## G36 personalized GitHub guidance and memory

`src/riff/github_guidance.py` projects the latest bounded G26 snapshots into a
content-addressed delta with `NEW`, `CHANGED`, `UNCHANGED`, `DUPLICATE`, and
`UNAVAILABLE` states. Each delta retains snapshot IDs, source evidence IDs,
retrieval time, uncertainty, and parser/policy versions. A deterministic ranker
then returns at most three typed actions—`EXTEND_PROJECT`, `BUILD_GREENFIELD`,
`INVESTIGATE_GAP`, or `WAIT_FOR_EVIDENCE`—without inferring proficiency from
ownership or repository activity.

Migration 024 keeps guidance projections and feedback separate from immutable
evidence and project snapshots. `github_guidance_versions` links changed
inputs to a predecessor by version and fingerprint; `github_guidance_feedback`
is append-only and records acceptance, rejection, deferral, or correction with
the active policy version. The audit read names the five memory layers
explicitly: evidence ledger, project understanding, user decision memory,
guidance memory, and disposable conversation context. No raw repository body
or unrestricted conversation history is persisted by this feature.

The adapter, MCP, and terminal surfaces share the same repository boundary.
Guidance and audits are read-only; feedback requires the existing
`USER_CONFIRMED` token. Ambiguous project references fail closed and no action
creates an Exploration or mutates profile state.

## G37 goal-aware project guidance

`src/riff/project_goals.py` extracts only explicit goal, milestone, roadmap, and
next-step statements from bounded G26 artifacts. A goal projection carries its
source evidence, observed timestamp, parser/policy versions, and fingerprint;
changed wording creates a linked version in `github_project_goal_versions`.
`github_project_goal_events` stores user prioritization, completion, archival,
and correction decisions append-only and requires `USER_CONFIRMED` at the
adapter boundary. Repository identity is resolved separately from artifact
filenames and accepts `owner/name` or canonical URL references.

Goal guidance composes one selected projection with the G36 delta and optional
profile, decision, and opportunity slices. It returns at most three typed paths
and explicitly surfaces synthetic, stale, contradictory, or missing evidence
as uncertainty rather than proficiency claims.

## G38 raw-signal ingestion

`src/riff/raw_signal_ingestion.py` validates and replays a reviewed manifest of
cross-domain sources while reusing the G01 Evidence Receipt ledger. Signal
classes cover incident reports/postmortems, trajectory and reliability writing,
primary scientific papers, linked code/data, benchmarks, changelogs, and GitHub
discussion surfaces. Each item retains author/organization, canonical root,
publication time, linked artifact, version/commit, correlation group, and an
evidence role (`PRIMARY_EVIDENCE`, `SECONDARY_SYNTHESIS`, or `USER_LEAD`).

Fixture and secondary leads are explicitly marked and cannot inflate independent
roots or confidence. Full raw bodies remain persisted for provenance but are not
sent to the model by ingestion. The terminal fixture runner shares the same
idempotent `EvidenceRepository` path used by scheduled collection, while all
manifest sources remain disabled until separately reviewed.

## G27 project-aware recommendations

`src/riff/recommendations.py` compares a bounded Riff/profile slice with
user-approved G26 project snapshots using a deterministic, versioned policy.
Capability and technology overlap, purpose/seam text, project health, effort,
and scope risk remain inspectable fields; popularity and repository ownership
never become proficiency evidence. Each recommendation persists its signal and
project evidence IDs, snapshot ID, uncertainty, disposition, and input
fingerprint in `project_recommendations`, so identical matches are idempotent
and changed snapshots produce new recommendation inputs.

The adapter and native MCP surface expose bounded project listing, inspection,
matching, override, and extension operations. Matching is read-only. A user
confirmation and the existing user `APPROVE_EXPLORATION` decision are both
required before an extension attaches a stable project ID to an Exploration;
PRD approval remains separate. Greenfield/defer overrides preserve the
original recommendation and do not mutate GitHub, profile state, or source
collection.

## G28 opportunity context and execution riffing

`src/riff/opportunities.py` separates an opportunity's actors, workflow,
platforms, connectors, permissions, approvals, security boundaries, success
measures, and unknowns from capability claims. Structured fixtures are
deterministically extracted into versioned `opportunities` records with source
evidence and input hashes; named platforms such as Perplexity Computer remain
constraints of that opportunity rather than universal implementation choices.

Three bounded execution candidates are generated with project seams when a
credible seam is supplied, plus greenfield and failure-first alternatives.
`COMBINE`, `EXTEND`, `NARROW`, `INVERT`, `TRANSFER`, and `CONSTRAIN` create
parent-linked immutable variants in `execution_candidates`. Comparison scores
remain deterministic and inspectable. The adapter/MCP and terminal surfaces
can record a selected direction, but selection never creates an Exploration or
PRD; those existing approvals remain the next authority boundary.
