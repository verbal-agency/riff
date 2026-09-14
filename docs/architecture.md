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
