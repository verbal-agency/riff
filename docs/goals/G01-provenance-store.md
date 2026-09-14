# G01 — Build the provenance-first evidence store

**Status:** Complete
**Depends on:** G00  
**Unlocks:** G02  
**PRD references:** Sections 7–9, 21–22, 26–27

## Outcome

Riff can persist, retrieve, deduplicate, and search raw external evidence without losing its origin. The schema establishes durable identities and provenance relationships that later extraction and argument-generation stages can reference.

## User-visible proof

Given repeated and overlapping evidence inputs, an operator can see which records were newly stored, which were exact/canonical duplicates, where each item came from, and retrieve the original material behind a stored ID.

## Inputs

- G00's application, database, migration, configuration, and test seams.
- Representative raw job, GitHub, article, and discovery-link fixtures.

## Project outcomes and scenarios advanced

- **Outcomes:** incremental three-source evidence foundation; durable provenance; searchable raw-source retrieval.
- **Scenarios:** `SC-EVIDENCE-001` and the evidence/provenance portions of `SC-DOGFOOD-001`.

## Scope

- Define source, source-item, raw-evidence, retrieval, and provenance records.
- Represent source type, author, organization, publication and retrieval dates, canonical URL, content hash, raw content or snapshot location, and source-native identity.
- Store root-source relationships separately from discovery/referrer relationships.
- Support exact deduplication by source identity, canonical URL, and content hash without erasing distinct observations.
- Provide repository/application methods for idempotent writes, retrieval by ID, and metadata/full-text search suitable for the expected single-user corpus.
- Define stable evidence IDs that can later be cited by claims and Riffs.
- Specify retention and redaction behavior for stored payloads and logs.

## Non-goals

- Semantic similarity deduplication, receipt extraction, embeddings, capability mapping, or signal ranking.
- Live source adapters.
- Treating repeated retrievals as independent evidence.

## Required properties

- Raw evidence is immutable after successful collection. A changed remote item becomes a new version linked to the prior version.
- Discovery location is not assumed to be the root information source.
- Deduplication decisions are inspectable and do not discard provenance.
- Every downstream-citable record can resolve to stored source metadata and raw content/snapshot.
- Payload contents and private data do not appear in routine logs.

## Deliverables

- Database migrations for evidence and provenance entities.
- Domain types and persistence operations.
- Canonicalization and content-hashing policy with tests.
- Search/retrieval application operations.
- Deterministic fixtures covering duplicate, versioned, discovered-through, and malformed evidence.

## Acceptance criteria

- [x] Re-ingesting the same source-native item, canonical URL, and content produces no duplicate raw-evidence row and reports an idempotent result.
- [x] Changed content at the same canonical source creates a linked version while preserving the earlier snapshot and retrieval record.
- [x] Two pages that point to the same root artifact can retain separate discovery provenance while sharing the identified root source.
- [x] Evidence is retrievable by stable ID with canonical URL, source, dates, hash, and raw content/snapshot reference intact.
- [x] Search can filter by source type and date and can find representative stored text without a separate vector database.
- [x] Canonicalization does not merge materially different source-native items merely because their normalized URLs are similar.
- [x] Postgres integration tests prove uniqueness, versioning, provenance traversal, and search behavior.

## Verification evidence

Use a fixture set that includes tracking-parameter URL variants, an updated article/repository snapshot, identical content mirrored at two URLs, and an HN-like discovery link to an original artifact. Show the stored row/provenance counts expected for each case.

## Implementation latitude

The exact table layout and whether raw content is stored inline or behind a storage interface are implementation choices. For v0.1, local/Postgres storage is preferable to adding object-storage infrastructure unless size evidence demands otherwise.

## Cycle verification (2026-09-14)

- `.venv/bin/python -m pytest` → **15 passed, 7 skipped** without a configured database; skips are the opt-in Postgres tests.
- Against an isolated temporary PostgreSQL instance, `.venv/bin/python -m riff migrate` applied `001_initial` and `002_evidence_store`; `.venv/bin/python -m pytest -m postgres` → **7 passed**.
- The Postgres suite covered `test_duplicate_source_item_is_idempotent`, `test_changed_content_creates_version`, `test_discovery_edge_preserves_root`, `test_retrieve_by_id_and_search_metadata`, `test_url_variants_do_not_merge_distinct_native_items`, and `test_evidence_constraints_and_transaction_rollback`, plus the foundation migration idempotence test.
- `git diff --check` and `.venv/bin/python -m compileall -q src tests` passed.

## Execution contract for the next Luna run

### Expected implementation surface

Luna should extend the existing `src/riff` package with evidence/provenance domain types, repositories, canonicalization utilities, and application operations. Add the next numbered SQL migration under `src/riff/migrations/`. Add focused tests in `tests/test_evidence_store.py` (or an equivalent clearly named module), Postgres integration coverage in `tests/test_evidence_store_postgres.py`, and update `docs/architecture.md` or a focused evidence design note with the persisted contract. Equivalent module paths are allowed only when the completion report names them and preserves the public behavior below.

### Canonical domain and persistence contract

Use schema version `1` for this goal. The persisted contract must expose these concepts and required fields, whether represented as tables or equivalent repository records:

| Concept | Required fields | Invariants |
|---|---|---|
| Source | `source_id`, `source_type`, `name`, `canonical_root` (nullable), `enabled` | `source_type` is one of `JOBS`, `GITHUB`, `TECHNICAL_WRITING`, `DISCOVERY`; source identity is stable. |
| Source item | `source_item_id`, `source_id`, `native_id` (nullable), `canonical_url`, `title` (nullable) | A source-native item is uniquely addressable; URL canonicalization is deterministic. |
| Raw evidence version | `evidence_id`, `source_item_id`, `content_hash`, `retrieved_at`, `published_at` (nullable), `raw_content` or `snapshot_ref`, `schema_version` | Evidence is immutable; a changed content hash creates a linked version, never an overwrite. |
| Retrieval | `retrieval_id`, `evidence_id`, `retrieved_at`, `outcome`, `metadata` | Every collection attempt has an inspectable outcome; failed attempts cannot masquerade as evidence. |
| Provenance edge | `edge_id`, `from_id`, `to_id`, `relationship`, `created_at` | `relationship` distinguishes `DISCOVERED_THROUGH`, `VERSION_OF`, and `CONTENT_EQUIVALENT`; edges cannot point to missing records. |

`source_type`, retrieval outcome, and provenance relationship values must reject unknown values. An evidence record must have exactly one source-item identity, a nonempty content hash, and either inline raw content or a nonempty snapshot reference. A source item may have many versions and retrievals. A content-equivalent mirror remains a distinct source item/root; equivalence must not merge its provenance or make it an independent root source by accident.

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| Same source-native ID, canonical URL, and content hash | Return the existing `evidence_id`; create no duplicate evidence/version; retain one new retrieval outcome if supplied. |
| Same source item and URL, changed content hash | Create one new immutable version linked by `VERSION_OF`; preserve the prior version. |
| Tracking/query URL variants that canonicalize identically | Resolve to one source-item identity and follow the same idempotence rule. |
| Distinct non-null provider-native IDs sharing one normalized URL | Keep separate source items; native identity takes precedence over URL-only matching. |
| Identical content at two distinct root URLs | Keep distinct source items and provenance; optionally add `CONTENT_EQUIVALENT`, never collapse roots. |
| Discovery page linking to an original artifact | Persist the discovery item and an explicit `DISCOVERED_THROUGH` edge to the original/root item. |
| Missing source type, URL/native identity, hash, or content/snapshot | Reject/quarantine with a typed validation outcome and perform no partial evidence write. |
| Concurrent writes for one logical identity | Database uniqueness/transaction rules yield one durable evidence identity; the loser is an idempotent result, not an error that corrupts state. |
| Search by source type/date/text | Return stable IDs and metadata; full raw payload is loaded only when explicitly requested. |

### Authority and side-effect boundaries

This goal may mutate only Riff's local Postgres schema and evidence records through application repositories. It must not fetch the network, write to target repositories, invoke models, run subprocesses, publish user-facing Riffs, or make approval/lifecycle decisions. Tests use offline fixtures and an explicitly supplied test database; no credential is read except the test database URL. Raw payloads and any private values must not appear in routine logs.

### Offline fixtures and state controls

Add recorded fixtures for: a valid article/job/GitHub item; duplicate URL/hash; tracking-URL variants; changed version; identical mirror; discovery-to-root edge; malformed/missing fields; conflicting metadata; unsupported source type; and a transaction failure/partial-write simulation. Test replay of the same fixture, duplicate calls, version invalidation, and rollback. G01 has no model or expensive-work budget, so budget-exhaustion and model-cache fixtures are not applicable; document that boundary rather than inventing budget behavior. No live network fixture is permitted in the normal suite.

### Criterion-to-test/artifact map

The completion report must name the concrete proof for each criterion:

| G01 criterion | Required proof artifact |
|---|---|
| Idempotent duplicate handling | `test_duplicate_source_item_is_idempotent` and Postgres uniqueness assertion |
| Immutable changed version | `test_changed_content_creates_version` plus version/provenance query output |
| Discovery/root provenance | `test_discovery_edge_preserves_root` |
| Stable retrieval/search | `test_retrieve_by_id_and_search_metadata` |
| Canonicalization safety | `test_url_variants_canonicalize_without_merging_distinct_items` |
| Postgres integrity | `test_evidence_constraints_and_transaction_rollback` in the marked integration module |
