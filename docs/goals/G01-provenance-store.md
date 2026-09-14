# G01 — Build the provenance-first evidence store

**Status:** Queued  
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

- [ ] Re-ingesting the same source-native item, canonical URL, and content produces no duplicate raw-evidence row and reports an idempotent result.
- [ ] Changed content at the same canonical source creates a linked version while preserving the earlier snapshot and retrieval record.
- [ ] Two pages that point to the same root artifact can retain separate discovery provenance while sharing the identified root source.
- [ ] Evidence is retrievable by stable ID with canonical URL, source, dates, hash, and raw content/snapshot reference intact.
- [ ] Search can filter by source type and date and can find representative stored text without a separate vector database.
- [ ] Canonicalization does not merge materially different source-native items merely because their normalized URLs are similar.
- [ ] Postgres integration tests prove uniqueness, versioning, provenance traversal, and search behavior.

## Verification evidence

Use a fixture set that includes tracking-parameter URL variants, an updated article/repository snapshot, identical content mirrored at two URLs, and an HN-like discovery link to an original artifact. Show the stored row/provenance counts expected for each case.

## Implementation latitude

The exact table layout and whether raw content is stored inline or behind a storage interface are implementation choices. For v0.1, local/Postgres storage is preferable to adding object-storage infrastructure unless size evidence demands otherwise.
