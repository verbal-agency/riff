# G06 — Separate and reversibly normalize capabilities and technologies

**Status:** Queued  
**Depends on:** G05  
**Unlocks:** G07, G08  
**PRD references:** Sections 8.3, 11–12, 24.2–24.3

## Outcome

Riff maintains an inspectable capability graph that groups synonymous evidence candidates without collapsing distinct engineering abilities, while keeping concrete technologies and their relationships separate.

## User-visible proof

Given fixture phrases such as “checkpoint recovery,” “resumable agents,” and “workflow replay,” Riff can suggest or establish a relationship to durable agent execution, while “agent memory” remains distinct unless evidence justifies a relationship.

## Inputs

- Versioned G05 receipts containing candidate capability and technology terms.
- Labeled synonym, adjacency, framework-fragmentation, and over-merge cases.

## Scope

- Define capability, technology, concept, pattern, alias, relationship, and candidate-mapping records.
- Preserve candidate text and evidence provenance for every proposed mapping.
- Represent match confidence and status such as proposed, accepted, rejected, or superseded.
- Support merge, split, alias, and remap operations without rewriting source receipts or losing history.
- Seed only the minimal ontology needed by fixtures/dogfood; do not create a grand taxonomy upfront.
- Add normalization evaluation cases for synonym grouping, adjacent concepts, framework fragmentation, and over-merging.
- Expose application operations to inspect a capability and its concepts, patterns, technologies, evidence, and mapping rationale.

## Non-goals

- User proficiency, trend ranking, autonomous irreversible taxonomy edits, or a graph database.
- Equating a technology mention with evidence of the underlying capability.

## Required properties

- Capabilities are phrased as transferable abilities, not product names.
- Technologies can relate to multiple capabilities and vice versa.
- Low-confidence mappings remain candidates; they do not silently alter canonical counts.
- Every accepted relationship is reversible and auditable.
- Normalization is stable under repeated runs over unchanged receipts.

## Deliverables

- Relational capability/technology graph schema and migrations.
- Candidate-mapping and review/decision operations.
- Normalization implementation behind a replaceable deterministic/model-assisted boundary.
- Labeled positive, negative, ambiguous, merge, and split fixtures with evaluation report.

## Acceptance criteria

- [ ] The checkpoint/replay/recovery fixture maps to a coherent durable-execution capability at the expected confidence/status.
- [ ] Agent memory and workflow persistence are not automatically merged in the negative fixture.
- [ ] Multiple frameworks implementing one bounded pattern strengthen one capability candidate without becoming separate capability nodes solely because names differ.
- [ ] A reviewer can accept, reject, remap, split, and undo a mapping while all original receipt provenance remains intact.
- [ ] Technology-to-capability relationships are many-to-many and queryable in both directions.
- [ ] Reprocessing unchanged candidates does not create duplicate nodes or relationships.
- [ ] The evaluation report presents under-merging and over-merging separately and includes the exact failing cases.

## Verification evidence

Demonstrate the PRD's durable-execution and agent-memory examples plus at least one ambiguous technology/capability fixture. Show graph state before, after, and after undoing a mapping decision.

## Implementation latitude

Relational adjacency tables are sufficient. Semantic retrieval may use Postgres/pgvector only if justified by observed normalization needs; deterministic aliases and constrained model reasoning should be considered first.
